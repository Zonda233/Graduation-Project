from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .INodePlacer import INodePlacer
from .RouterInputModels import NodeSpec, RouterInput
from .VoxelGeometryMaps import VoxelGeometryMaps
from .config import RouterConfig
from .constants import DEFAULT_SEED_NORM_XY, MIN_FREE_ANCHOR_RADIUS
from .domain_types import PlacedNode, Vc, Wc


@dataclass
class SimpleNodePlacer(INodePlacer):
    """Voxel-level NodePlacer with topology fallback and coarse AABB collision checks."""

    DEFAULT_EQUIPMENT_EXTENT: Tuple[int, int, int] = (3, 3, 3)
    DEFAULT_NODE_EXTENT: Tuple[int, int, int] = (1, 1, 1)

    last_report: Dict[str, Any] = field(default_factory=dict)

    def place_nodes(self, router_input: RouterInput, config: RouterConfig) -> Dict[str, PlacedNode]:
        nodes = list(router_input.nodes)
        _, _, nz = config.grid_dimensions
        placed: Dict[str, PlacedNode] = {}
        occupied: Set[Vc] = set()
        conflicts: List[Dict[str, object]] = []
        topology_seeds = self._topology_seed_map(router_input)
        spatial_rules = router_input.constraints.spatial_rules
        default_clearance = int(spatial_rules.default_clearance_voxels)
        max_search_radius = int(spatial_rules.max_search_radius_voxels)
        default_z_layers = [int(z) for z in spatial_rules.default_z_layers if 0 <= int(z) < nz] or [0]

        for node in nodes:
            placed_node, conflict = self._place_single_node(
                node=node,
                config=config,
                topology_seeds=topology_seeds,
                default_z_layers=default_z_layers,
                default_clearance=default_clearance,
                max_search_radius=max_search_radius,
                occupied=occupied,
            )
            placed[node.node_id] = placed_node
            if conflict:
                conflicts.append(conflict)

        self.last_report = {
            "placed_nodes": len(placed),
            "occupied_voxels": len(occupied),
            "conflicts": conflicts,
            "seed_mode": "location_2d_or_topology_auto",
        }
        return placed

    def _place_single_node(
        self,
        node: NodeSpec,
        config: RouterConfig,
        topology_seeds: Dict[str, Tuple[float, float]],
        default_z_layers: List[int],
        default_clearance: int,
        max_search_radius: int,
        occupied: Set[Vc],
    ) -> Tuple[PlacedNode, Optional[Dict[str, object]]]:
        seed_xy_norm, seed_source = self._resolve_seed_xy(node, topology_seeds)
        seed_xy_voxel = self._to_seed_voxel(seed_xy_norm, config.grid_dimensions)
        direction = self._resolve_direction(node)

        _, _, nz = config.grid_dimensions
        candidate_layers = self._candidate_layers(node, default_z_layers, nz)
        if direction == "-Z" and 1 not in candidate_layers and nz > 1:
            candidate_layers = [1] + candidate_layers

        extent = self._extent_voxels(node)
        clearance = self._resolve_clearance(node, default_clearance)
        node_max_radius = self._search_radius(node, max_search_radius)
        anchor = self._find_anchor(
            seed_xy=seed_xy_voxel,
            layers=candidate_layers,
            extent=extent,
            clearance=clearance,
            occupied=occupied,
            grid_dimensions=config.grid_dimensions,
            max_search_radius=node_max_radius,
        )

        conflict: Optional[Dict[str, object]] = None
        if anchor is None:
            fallback_z = candidate_layers[0] if candidate_layers else 0
            anchor = (seed_xy_voxel[0], seed_xy_voxel[1], fallback_z)
            conflict = {
                "node_id": node.node_id,
                "reason": "placement_search_failed_fallback_to_seed",
                "seed_xy": [seed_xy_voxel[0], seed_xy_voxel[1]],
                "seed_source": seed_source,
                "fallback_vc": list(anchor),
            }

        occupied.update(self._expanded_box_voxels(anchor, extent, clearance, config.grid_dimensions))
        wc = self._vc_to_wc(anchor, config)
        return (
            PlacedNode(node_id=node.node_id, vc=anchor, wc=wc, direction=direction),
            conflict,
        )

    def _resolve_seed_xy(
        self,
        node: NodeSpec,
        topology_seeds: Dict[str, Tuple[float, float]],
    ) -> Tuple[Tuple[float, float], str]:
        if node.location_2d_x is not None and node.location_2d_y is not None:
            return (float(node.location_2d_x), float(node.location_2d_y)), "location_2d"
        return topology_seeds.get(node.node_id, DEFAULT_SEED_NORM_XY), "topology_auto"

    @staticmethod
    def _to_seed_voxel(seed_xy_norm: Tuple[float, float], grid_dimensions: Tuple[int, int, int]) -> Tuple[int, int]:
        nx, ny, _ = grid_dimensions
        x_norm, y_norm = seed_xy_norm
        vx = min(max(int(x_norm * nx), 0), nx - 1)
        vy = min(max(int(y_norm * ny), 0), ny - 1)
        return vx, vy

    def _resolve_direction(self, node: NodeSpec) -> Optional[str]:
        pref_dir = node.placement_hint.direction_preferred
        if isinstance(pref_dir, str) and pref_dir in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}:
            return pref_dir
        if self._is_tank_outlet(node):
            return "-Z"
        return None

    @staticmethod
    def _resolve_clearance(node: NodeSpec, default_clearance: int) -> int:
        if node.bbox_hint.clearance_voxels is None:
            return default_clearance
        return int(node.bbox_hint.clearance_voxels)

    @staticmethod
    def _vc_to_wc(vc: Vc, config: RouterConfig) -> Wc:
        wc = VoxelGeometryMaps.vc_to_wc(vc, config)
        return (wc[0], wc[1], wc[2])

    def _is_tank_outlet(self, node: Any) -> bool:
        return node.node_type == "EquipmentPort" and node.role == "outlet"

    def _candidate_layers(self, node: Any, default_layers: List[int], nz: int) -> List[int]:
        raw_layers = node.placement_hint.z_layers
        if raw_layers is None:
            return [1] if (self._is_tank_outlet(node) and nz > 1) else list(default_layers)
        layers = [int(z) for z in raw_layers if 0 <= int(z) < nz]
        return layers or list(default_layers)

    def _search_radius(self, node: Any, default_radius: int) -> int:
        policy = node.placement_hint.anchor_policy
        if policy == "fixed":
            return 0
        if policy == "free":
            return max(default_radius, MIN_FREE_ANCHOR_RADIUS)
        return default_radius

    def _extent_voxels(self, node: Any) -> Tuple[int, int, int]:
        raw = node.bbox_hint.extent_voxels
        if isinstance(raw, list) and len(raw) == 3:
            ex, ey, ez = int(raw[0]), int(raw[1]), int(raw[2])
            return (max(1, ex), max(1, ey), max(1, ez))
        if node.node_type == "Equipment":
            return self.DEFAULT_EQUIPMENT_EXTENT
        return self.DEFAULT_NODE_EXTENT

    def _expanded_box_voxels(
        self,
        anchor: Vc,
        extent: Tuple[int, int, int],
        clearance: int,
        grid_dimensions: Tuple[int, int, int],
    ) -> Set[Vc]:
        ex, ey, ez = extent
        min_x = anchor[0] - ex // 2 - clearance
        min_y = anchor[1] - ey // 2 - clearance
        min_z = anchor[2] - ez // 2 - clearance
        max_x = min_x + ex - 1 + 2 * clearance
        max_y = min_y + ey - 1 + 2 * clearance
        max_z = min_z + ez - 1 + 2 * clearance
        nx, ny, nz = grid_dimensions
        voxels: Set[Vc] = set()
        for x in range(min_x, max_x + 1):
            if x < 0 or x >= nx:
                continue
            for y in range(min_y, max_y + 1):
                if y < 0 or y >= ny:
                    continue
                for z in range(min_z, max_z + 1):
                    if z < 0 or z >= nz:
                        continue
                    voxels.add((x, y, z))
        return voxels

    def _is_box_in_bounds(
        self,
        anchor: Vc,
        extent: Tuple[int, int, int],
        grid_dimensions: Tuple[int, int, int],
    ) -> bool:
        ex, ey, ez = extent
        min_x = anchor[0] - ex // 2
        min_y = anchor[1] - ey // 2
        min_z = anchor[2] - ez // 2
        max_x = min_x + ex - 1
        max_y = min_y + ey - 1
        max_z = min_z + ez - 1
        nx, ny, nz = grid_dimensions
        return min_x >= 0 and min_y >= 0 and min_z >= 0 and max_x < nx and max_y < ny and max_z < nz

    def _is_anchor_free(
        self,
        anchor: Vc,
        extent: Tuple[int, int, int],
        clearance: int,
        occupied: Set[Vc],
        grid_dimensions: Tuple[int, int, int],
    ) -> bool:
        if not self._is_box_in_bounds(anchor, extent, grid_dimensions):
            return False
        check_voxels = self._expanded_box_voxels(anchor, extent, clearance, grid_dimensions)
        return all(v not in occupied for v in check_voxels)

    def _candidate_xy_offsets(self, radius: int) -> Iterable[Tuple[int, int]]:
        if radius == 0:
            yield (0, 0)
            return
        for d in range(1, radius + 1):
            for dx in range(-d, d + 1):
                for dy in range(-d, d + 1):
                    if max(abs(dx), abs(dy)) == d:
                        yield (dx, dy)

    def _find_anchor(
        self,
        seed_xy: Tuple[int, int],
        layers: List[int],
        extent: Tuple[int, int, int],
        clearance: int,
        occupied: Set[Vc],
        grid_dimensions: Tuple[int, int, int],
        max_search_radius: int,
    ) -> Optional[Vc]:
        sx, sy = seed_xy
        for radius in range(0, max_search_radius + 1):
            for z in layers:
                for dx, dy in self._candidate_xy_offsets(radius):
                    vc = (sx + dx, sy + dy, z)
                    if self._is_anchor_free(vc, extent, clearance, occupied, grid_dimensions):
                        return vc
        return None

    def _topology_seed_map(self, router_input: RouterInput) -> Dict[str, Tuple[float, float]]:
        """对外接口：返回节点 ID 到 (x, y) 归一化坐标的映射"""
        nodes = list(router_input.nodes)
        node_ids = [n.node_id for n in nodes]
        if not node_ids:
            return {}

        # 1. 构建邻接表与入度
        adj_info = self._build_adjacency_and_indeg(router_input, node_ids)

        # 2. 拓扑排序并计算深度
        topo_order, depth = self._topological_sort_with_depth(adj_info)

        # 3. 处理孤立节点（未在拓扑排序中的）
        topo_order = self._append_isolated_nodes(topo_order, node_ids)

        # 4. 按深度分组并对同层节点排序（基于前驱的 y 坐标）
        levels = self._group_and_sort_by_depth(topo_order, depth, adj_info.in_adj)

        # 5. 计算种子坐标
        seeds = self._compute_seed_coordinates(levels, depth, adj_info.in_adj)
        return seeds
        
    # 坐标归一化参数
    X_START = 0.12
    X_END = 0.76
    Y_BASE = 0.18
    Y_RANGE = 0.64
    Y_CENTER = 0.5
    X_LEVEL_JITTER_FACTOR = 0.22

    @dataclass
    class AdjacencyInfo:
        """邻接表与入度信息"""
        out_adj: Dict[str, List[str]]
        in_adj: Dict[str, List[str]]
        indeg: Dict[str, int]

    def _build_adjacency_and_indeg(
        self, router_input: RouterInput, node_ids: List[str]
    ) -> AdjacencyInfo:
        """根据 lines 构建邻接表与入度"""
        out_adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        in_adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        indeg: Dict[str, int] = {nid: 0 for nid in node_ids}

        for line in router_input.lines:
            chain = [line.from_node_id] + list(line.via_node_ids) + [line.to_node_id]
            # 只保留存在的节点
            chain = [nid for nid in chain if nid in indeg]
            for i in range(len(chain) - 1):
                u, v = chain[i], chain[i + 1]
                if v not in out_adj[u]:
                    out_adj[u].append(v)
                    in_adj[v].append(u)
                    indeg[v] += 1

        return self.AdjacencyInfo(out_adj, in_adj, indeg)

    def _topological_sort_with_depth(
        self, adj_info: AdjacencyInfo
    ) -> Tuple[List[str], Dict[str, int]]:
        """拓扑排序，同时计算每个节点的最长路径深度"""
        indeg_work: dict[str, int] = adj_info.indeg
        queue = sorted([nid for nid, d in indeg_work.items() if d == 0])
        topo_order: List[str] = []
        depth: dict[str, int] = {nid : 0 for nid in adj_info.out_adj.keys()}

        while queue:
            u: str = queue.pop(0)
            topo_order.append(u)
            for v in adj_info.out_adj[u]:
                depth[v] = max(depth[v], depth[u] + 1)
                indeg_work[v] -= 1
                if indeg_work[v] == 0:
                    queue.append(v)
            queue.sort()

        return topo_order, depth

    def _append_isolated_nodes(self, topo_order: List[str], all_node_ids: List[str]) -> List[str]:
        """将未出现在拓扑排序中的孤立节点追加到末尾"""
        visited = set(topo_order)
        for nid in sorted(all_node_ids):
            if nid not in visited:
                topo_order.append(nid)
        return topo_order

    def _group_and_sort_by_depth(
        self,
        topo_order: List[str],
        depth: Dict[str, int],
        in_adj: Dict[str, List[str]],
    ) -> Dict[int, List[str]]:
        """按深度分组，并对同层节点进行基于前驱 barycenter 的排序"""
        # 先分组
        by_depth: Dict[int, List[str]] = {}
        for nid in topo_order:
            d = depth.get(nid, 0)
            by_depth.setdefault(d, []).append(nid)

        y_rank: Dict[str, float] = {}
        for d in sorted(by_depth.keys()):
            level_nodes = by_depth[d]
            sortable: List[Tuple[float, str]] = []
            for nid in level_nodes:
                preds = in_adj.get(nid, [])
                if preds:
                    known = [y_rank[p] for p in preds if p in y_rank]
                    bary = sum(known) / len(known) if known else float(len(sortable))
                else:
                    bary = float(len(sortable))
                sortable.append((bary, nid))
            sortable.sort(key=lambda x: (x[0], x[1]))
            by_depth[d] = [nid for _, nid in sortable]
            for idx, nid in enumerate(by_depth[d]):
                y_rank[nid] = float(idx)
        
        return by_depth

    def _compute_seed_coordinates(
        self,
        levels: Dict[int, List[str]],
        depth: Dict[str, int],
        in_adj: Dict[str, List[str]],
    ) -> Dict[str, Tuple[float, float]]:
        """根据深度和层内索引计算归一化坐标"""
        max_depth = max(levels.keys()) if levels else 0
        seeds: Dict[str, Tuple[float, float]] = {}

        for d in sorted(levels.keys()):
            node_list = levels[d]
            k = len(node_list)
            for i, nid in enumerate(node_list):
                depth_ratio = d / max(1, max_depth)
                # 在同一深度层内做轻微 x 去重，避免所有同层节点完全同 x。
                if k > 1:
                    x_jitter = self.X_LEVEL_JITTER_FACTOR * (i / (k - 1) - 0.5)
                else:
                    x_jitter = 0.0
                x_norm = self.X_START + self.X_END * depth_ratio + x_jitter * (self.X_END / max(1, max_depth))

                # 单节点层不再固定落在中线，而是尽量继承前驱节点的 y（如果有）。
                preds = in_adj.get(nid, [])
                pred_ys = [seeds[p][1] for p in preds if p in seeds]
                if k == 1 and pred_ys:
                    y_norm = sum(pred_ys) / len(pred_ys)
                elif k == 1:
                    y_norm = self.Y_CENTER
                else:
                    y_norm = self.Y_BASE + self.Y_RANGE * (i / (k - 1))

                x_norm = min(max(x_norm, 0.02), 0.98)
                y_norm = min(max(y_norm, 0.02), 0.98)
                seeds[nid] = (x_norm, y_norm)

        return seeds
