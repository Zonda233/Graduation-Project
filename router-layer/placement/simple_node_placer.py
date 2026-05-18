from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..config import RouterConfig
from ..constants import DEFAULT_SEED_NORM_XY, MIN_FREE_ANCHOR_RADIUS
from ..grid.voxel_geometry import VoxelGeometryMaps
from ..models.domain_types import PlacedNode, PlacedNodeMap
from ..models.input_models import NodeSpec, RouterInput
from ..models.types import Vc, Wc


@dataclass
class SimpleNodePlacer:
    """Voxel-level node placer with topology fallback and coarse AABB collision checks.

    Multi-port tank placement (Bug 14 fix)
    ----------------------------------------
    When multiple EquipmentPort nodes share the same ``equipment_ref`` they are
    placed as a coherent group rather than independently:

    * **Anchor port** (first in the group) is placed normally via the standard
      seed/search logic.  Its direction is ``direction_preferred`` if set,
      otherwise ``-Z`` (bottom nozzle).
    * **Shell nozzles** (remaining ports) are placed at a fixed radial offset
      from the anchor's XY position so that the pipe connects flush to the
      cylindrical shell surface.  The offset is
      ``ceil(SHELL_RADIUS / voxel_size)`` voxels in X or Y.  Direction cycles
      through ``[+X, -X, +Y, -Y]`` unless ``direction_preferred`` is set.
    """

    DEFAULT_EQUIPMENT_EXTENT: Tuple[int, int, int] = (3, 3, 3)
    DEFAULT_NODE_EXTENT: Tuple[int, int, int] = (1, 1, 1)

    # Radial directions used for shell nozzles (in order)
    _SHELL_DIRECTIONS: Tuple[str, ...] = ("+X", "-X", "+Y", "-Y")

    last_report: Dict[str, Any] = field(default_factory=dict)

    def place_nodes(self, router_input: RouterInput, config: RouterConfig) -> PlacedNodeMap:
        nodes = list(router_input.nodes)
        _, _, nz = config.grid_dimensions
        placed: PlacedNodeMap = {}
        occupied: Set[Vc] = set()
        conflicts: List[Dict[str, object]] = []
        topology_seeds = self._topology_seed_map(router_input)
        spatial_rules = router_input.constraints.spatial_rules
        default_clearance = int(spatial_rules.default_clearance_voxels)
        max_search_radius = int(spatial_rules.max_search_radius_voxels)
        default_z_layers = [int(z) for z in spatial_rules.default_z_layers if 0 <= int(z) < nz] or [0]

        # Pre-pass: group EquipmentPort nodes by equipment_ref.
        # Signal ports (role=signal / port_kind=instrument_tap / snap_to_shell)
        # are intentionally excluded here — they are placed individually by the
        # main loop below and then repositioned by EquipmentPortShellSnapper.
        # Including them in the group would assign a fixed radial direction (+X
        # etc.) that conflicts with the shell-snapper's cylindrical projection,
        # causing no_path_found failures (Bug 15).
        equipment_groups: Dict[str, List[NodeSpec]] = {}
        for node in nodes:
            if node.node_type == "EquipmentPort" and node.equipment_ref:
                if not self._is_signal_port(node):
                    equipment_groups.setdefault(node.equipment_ref, []).append(node)

        # IDs that will be placed by the group logic (skip in the main loop)
        group_placed_ids: Set[str] = set()

        for eid, group_nodes in equipment_groups.items():
            if len(group_nodes) >= 2:
                group_conflicts = self._place_equipment_group(
                    group_nodes=group_nodes,
                    config=config,
                    topology_seeds=topology_seeds,
                    default_z_layers=default_z_layers,
                    default_clearance=default_clearance,
                    max_search_radius=max_search_radius,
                    occupied=occupied,
                    placed=placed,
                )
                conflicts.extend(group_conflicts)
                for n in group_nodes:
                    group_placed_ids.add(n.node_id)

        for node in nodes:
            if node.node_id in group_placed_ids:
                continue
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

    # ------------------------------------------------------------------
    # Equipment-group two-phase placement (Bug 14)
    # ------------------------------------------------------------------

    def _place_equipment_group(
        self,
        group_nodes: List[NodeSpec],
        config: RouterConfig,
        topology_seeds: Dict[str, Tuple[float, float]],
        default_z_layers: List[int],
        default_clearance: int,
        max_search_radius: int,
        occupied: Set[Vc],
        placed: PlacedNodeMap,
    ) -> List[Dict[str, object]]:
        """Place a group of EquipmentPort nodes that share the same equipment_ref.

        Phase 1 – anchor port (group_nodes[0]):
            Placed normally.  Direction = direction_preferred or "-Z".

        Phase 2 – shell nozzles (group_nodes[1..N]):
            Placed at anchor_xy ± shell_radius_voxels in X or Y so the pipe
            connects flush to the cylindrical shell.  Direction cycles through
            [+X, -X, +Y, -Y] unless direction_preferred is set.
        """
        conflicts: List[Dict[str, object]] = []
        shell_radius_voxels = math.ceil(
            config.shell_radius / config.voxel_size
        )

        # ---- Phase 1: anchor port ----
        anchor_node = group_nodes[0]
        anchor_direction = self._resolve_direction_for_group_port(anchor_node, default_dir="-Z")
        anchor_placed, anchor_conflict = self._place_single_node(
            node=anchor_node,
            config=config,
            topology_seeds=topology_seeds,
            default_z_layers=default_z_layers,
            default_clearance=default_clearance,
            max_search_radius=max_search_radius,
            occupied=occupied,
            override_direction=anchor_direction,
        )
        placed[anchor_node.node_id] = anchor_placed
        if anchor_conflict:
            conflicts.append(anchor_conflict)

        anchor_vc = anchor_placed.vc  # (ax, ay, az)
        _, _, nz = config.grid_dimensions

        # ---- Phase 2: shell nozzles ----
        shell_dir_index = 0
        for shell_node in group_nodes[1:]:
            # Pick direction: prefer explicit hint, else cycle through radial dirs
            if (
                isinstance(shell_node.placement_hint.direction_preferred, str)
                and shell_node.placement_hint.direction_preferred in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}
            ):
                nozzle_dir = shell_node.placement_hint.direction_preferred
            else:
                nozzle_dir = self._SHELL_DIRECTIONS[shell_dir_index % len(self._SHELL_DIRECTIONS)]
                shell_dir_index += 1

            # Compute shell voxel position from anchor XY + radial offset
            dx, dy = self._direction_to_xy_delta(nozzle_dir)
            shell_vc = (
                anchor_vc[0] + dx * shell_radius_voxels,
                anchor_vc[1] + dy * shell_radius_voxels,
                anchor_vc[2],
            )
            # Clamp to grid bounds
            nx, ny, _ = config.grid_dimensions
            shell_vc = (
                min(max(shell_vc[0], 0), nx - 1),
                min(max(shell_vc[1], 0), ny - 1),
                min(max(shell_vc[2], 0), nz - 1),
            )
            wc = self._vc_to_wc(shell_vc, config)
            shell_placed = PlacedNode(
                node_id=shell_node.node_id,
                vc=shell_vc,
                wc=wc,
                direction=nozzle_dir,
            )
            placed[shell_node.node_id] = shell_placed
            occupied.update(
                self._expanded_box_voxels(
                    shell_vc,
                    self.DEFAULT_NODE_EXTENT,
                    default_clearance,
                    config.grid_dimensions,
                )
            )

        return conflicts

    @staticmethod
    def _resolve_direction_for_group_port(node: NodeSpec, default_dir: str) -> str:
        """Return direction_preferred if valid, else default_dir."""
        pref = node.placement_hint.direction_preferred
        if isinstance(pref, str) and pref in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}:
            return pref
        return default_dir

    @staticmethod
    def _direction_to_xy_delta(direction: str) -> Tuple[int, int]:
        """Map a cardinal direction string to (dx, dy) voxel offset."""
        return {
            "+X": (1, 0),
            "-X": (-1, 0),
            "+Y": (0, 1),
            "-Y": (0, -1),
            "+Z": (0, 0),
            "-Z": (0, 0),
        }.get(direction, (0, 0))

    @staticmethod
    def _is_signal_port(node: NodeSpec) -> bool:
        """Return True if *node* is a signal/instrument-tap port.

        Signal ports must NOT be included in the equipment-group placement
        pre-pass (Bug 15 fix).  They are placed individually by the main loop
        and then repositioned by :class:`~router_layer.snapping.shell_snapper.
        EquipmentPortShellSnapper`.
        """
        role = (node.role or "").strip().lower()
        if role == "signal":
            return True
        port_kind = str(node.properties.get("port_kind", "")).strip().lower()
        if port_kind == "instrument_tap":
            return True
        return bool(node.properties.get("snap_to_shell"))

    def _place_single_node(
        self,
        node: NodeSpec,
        config: RouterConfig,
        topology_seeds: Dict[str, Tuple[float, float]],
        default_z_layers: List[int],
        default_clearance: int,
        max_search_radius: int,
        occupied: Set[Vc],
        override_direction: Optional[str] = None,
    ) -> Tuple[PlacedNode, Optional[Dict[str, object]]]:
        seed_xy_norm, seed_source = self._resolve_seed_xy(node, topology_seeds)
        seed_xy_voxel = self._to_seed_voxel(seed_xy_norm, config.grid_dimensions)
        direction = override_direction if override_direction is not None else self._resolve_direction(node)

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
        return PlacedNode(node_id=node.node_id, vc=anchor, wc=wc, direction=direction), conflict

    def _resolve_seed_xy(
        self,
        node: NodeSpec,
        topology_seeds: Dict[str, Tuple[float, float]],
    ) -> Tuple[Tuple[float, float], str]:
        if node.location_2d_x is not None and node.location_2d_y is not None:
            return (float(node.location_2d_x), float(node.location_2d_y)), "location_2d"
        return topology_seeds.get(node.node_id, DEFAULT_SEED_NORM_XY), "topology_auto"

    @staticmethod
    def _to_seed_voxel(
        seed_xy_norm: Tuple[float, float],
        grid_dimensions: Tuple[int, int, int],
    ) -> Tuple[int, int]:
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

    @staticmethod
    def _is_tank_outlet(node: NodeSpec) -> bool:
        return node.node_type == "EquipmentPort" and node.role == "outlet"

    def _candidate_layers(self, node: NodeSpec, default_layers: List[int], nz: int) -> List[int]:
        raw_layers = node.placement_hint.z_layers
        if raw_layers is None:
            return [1] if (self._is_tank_outlet(node) and nz > 1) else list(default_layers)
        layers = [int(z) for z in raw_layers if 0 <= int(z) < nz]
        return layers or list(default_layers)

    def _search_radius(self, node: NodeSpec, default_radius: int) -> int:
        policy = node.placement_hint.anchor_policy
        if policy == "fixed":
            return 0
        if policy == "free":
            return max(default_radius, MIN_FREE_ANCHOR_RADIUS)
        return default_radius

    def _extent_voxels(self, node: NodeSpec) -> Tuple[int, int, int]:
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

    # ---------- topology seed map ----------

    X_START = 0.12
    X_END = 0.76
    Y_BASE = 0.18
    Y_RANGE = 0.64
    Y_CENTER = 0.5
    X_LEVEL_JITTER_FACTOR = 0.22

    @dataclass
    class _AdjacencyInfo:
        out_adj: Dict[str, List[str]]
        in_adj: Dict[str, List[str]]
        indeg: Dict[str, int]

    def _topology_seed_map(self, router_input: RouterInput) -> Dict[str, Tuple[float, float]]:
        nodes = list(router_input.nodes)
        node_ids = [n.node_id for n in nodes]
        if not node_ids:
            return {}
        adj = self._build_adjacency(router_input, node_ids)
        topo_order, depth = self._topological_sort(adj)
        topo_order = self._append_isolated(topo_order, node_ids)
        levels = self._group_by_depth(topo_order, depth, adj.in_adj)
        return self._compute_seeds(levels, depth, adj.in_adj)

    def _build_adjacency(
        self, router_input: RouterInput, node_ids: List[str]
    ) -> _AdjacencyInfo:
        out_adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        in_adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        indeg: Dict[str, int] = {nid: 0 for nid in node_ids}
        for line in router_input.lines:
            chain = [line.from_node_id] + list(line.via_node_ids) + [line.to_node_id]
            chain = [nid for nid in chain if nid in indeg]
            for i in range(len(chain) - 1):
                u, v = chain[i], chain[i + 1]
                if v not in out_adj[u]:
                    out_adj[u].append(v)
                    in_adj[v].append(u)
                    indeg[v] += 1
        return self._AdjacencyInfo(out_adj, in_adj, indeg)

    def _topological_sort(
        self, adj: _AdjacencyInfo
    ) -> Tuple[List[str], Dict[str, int]]:
        indeg_work = dict(adj.indeg)
        queue = sorted([nid for nid, d in indeg_work.items() if d == 0])
        topo_order: List[str] = []
        depth: Dict[str, int] = {nid: 0 for nid in adj.out_adj}
        while queue:
            u = queue.pop(0)
            topo_order.append(u)
            for v in adj.out_adj[u]:
                depth[v] = max(depth[v], depth[u] + 1)
                indeg_work[v] -= 1
                if indeg_work[v] == 0:
                    queue.append(v)
            queue.sort()
        return topo_order, depth

    @staticmethod
    def _append_isolated(topo_order: List[str], all_node_ids: List[str]) -> List[str]:
        visited = set(topo_order)
        for nid in sorted(all_node_ids):
            if nid not in visited:
                topo_order.append(nid)
        return topo_order

    def _group_by_depth(
        self,
        topo_order: List[str],
        depth: Dict[str, int],
        in_adj: Dict[str, List[str]],
    ) -> Dict[int, List[str]]:
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
                known = [y_rank[p] for p in preds if p in y_rank]
                bary = sum(known) / len(known) if known else float(len(sortable))
                sortable.append((bary, nid))
            sortable.sort(key=lambda x: (x[0], x[1]))
            by_depth[d] = [nid for _, nid in sortable]
            for idx, nid in enumerate(by_depth[d]):
                y_rank[nid] = float(idx)
        return by_depth

    def _compute_seeds(
        self,
        levels: Dict[int, List[str]],
        depth: Dict[str, int],
        in_adj: Dict[str, List[str]],
    ) -> Dict[str, Tuple[float, float]]:
        max_depth = max(levels.keys()) if levels else 0
        seeds: Dict[str, Tuple[float, float]] = {}
        for d in sorted(levels.keys()):
            node_list = levels[d]
            k = len(node_list)
            for i, nid in enumerate(node_list):
                depth_ratio = d / max(1, max_depth)
                x_jitter = self.X_LEVEL_JITTER_FACTOR * (i / (k - 1) - 0.5) if k > 1 else 0.0
                x_norm = self.X_START + self.X_END * depth_ratio + x_jitter * (self.X_END / max(1, max_depth))
                preds = in_adj.get(nid, [])
                pred_ys = [seeds[p][1] for p in preds if p in seeds]
                if k == 1 and pred_ys:
                    y_norm = sum(pred_ys) / len(pred_ys)
                elif k == 1:
                    y_norm = self.Y_CENTER
                else:
                    y_norm = self.Y_BASE + self.Y_RANGE * (i / (k - 1))
                seeds[nid] = (min(max(x_norm, 0.02), 0.98), min(max(y_norm, 0.02), 0.98))
        return seeds
