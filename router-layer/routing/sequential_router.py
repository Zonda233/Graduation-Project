from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from ..config import RouterConfig
from ..grid.grid import Grid3D
from ..models.domain_types import LineRouteMap, LineRouteResult, PlacedNode
from ..models.input_models import NodeSpec, RouterInput
from ..models.types import Vc
from ..pathfinding.path_finder import PathFinder


@dataclass
class SequentialMultiLineRouter:
    """Routes lines sequentially and blocks routed voxels for later lines."""

    def route_all_lines(
        self,
        grid: Grid3D,
        placed_nodes: Dict[str, PlacedNode],
        router_input: RouterInput,
        path_finder: PathFinder,
        config: RouterConfig,
    ) -> LineRouteMap:
        results: LineRouteMap = {}
        node_by_id: Dict[str, NodeSpec] = {n.node_id: n for n in router_input.nodes}
        static_forbidden = self._custom_module_blocked_voxels(router_input, placed_nodes, config)
        static_forbidden |= self._instrument_blocked_voxels(router_input, placed_nodes)
        forbidden: Set[Vc] = set(static_forbidden)
        for line in router_input.lines:
            line_id = line.line_id
            start_placed = placed_nodes[line.from_node_id]
            goal_placed = placed_nodes[line.to_node_id]
            goal_node = node_by_id.get(line.to_node_id)
            end_direction = goal_placed.direction
            if goal_node and self._is_custom_module_port(goal_node) and end_direction:
                end_direction = self._opposite_axis(end_direction)
            via_vc: List[Vc] = [placed_nodes[nid].vc for nid in line.via_node_ids]
            path = path_finder.find_path(
                grid=grid,
                start_vc=start_placed.vc,
                goal_vc=goal_placed.vc,
                via_vc=via_vc or None,
                forbidden=forbidden,
                line_ctx=line,
                start_direction=start_placed.direction,
                end_direction=end_direction,
            )
            if not path:
                results[line_id] = LineRouteResult(
                    line_id=line_id,
                    voxel_path=None,
                    success=False,
                    reason="no_path_found",
                )
                continue
            results[line_id] = LineRouteResult(
                line_id=line_id,
                voxel_path=path,
                success=True,
                reason=None,
            )
            forbidden.update(self._dilate_path(path, config.safety_margin_voxels))
        return results

    @staticmethod
    def _is_custom_module_port(node: NodeSpec) -> bool:
        asset_type = str(node.properties.get("asset_type", "")).strip().lower()
        module_kind = str(node.properties.get("module_kind", "")).strip().lower()
        return asset_type == "custom_module" or module_kind == "custom"

    @staticmethod
    def _opposite_axis(axis: str) -> str:
        return {
            "+X": "-X", "-X": "+X",
            "+Y": "-Y", "-Y": "+Y",
            "+Z": "-Z", "-Z": "+Z",
        }.get(axis, axis)

    def _custom_module_blocked_voxels(
        self,
        router_input: RouterInput,
        placed_nodes: Dict[str, PlacedNode],
        config: RouterConfig,
    ) -> Set[Vc]:
        groups: Dict[str, List[NodeSpec]] = {}
        for node in router_input.nodes:
            if node.node_type != "EquipmentPort" or not node.equipment_ref:
                continue
            if not self._is_custom_module_port(node):
                continue
            if node.node_id not in placed_nodes:
                continue
            groups.setdefault(node.equipment_ref, []).append(node)

        blocked: Set[Vc] = set()
        for nodes in groups.values():
            center_wc = self._infer_custom_center_wc(nodes, placed_nodes)
            center_vc = self._wc_to_vc(center_wc, config)
            extent = self._infer_custom_extent(nodes)
            ox = center_vc[0] - extent[0] // 2
            oy = center_vc[1] - extent[1] // 2
            oz = max(0, center_vc[2] - extent[2] // 2)
            for x in range(ox, ox + extent[0]):
                for y in range(oy, oy + extent[1]):
                    for z in range(oz, oz + extent[2]):
                        blocked.add((x, y, z))
        return blocked

    @staticmethod
    def _instrument_blocked_voxels(
        router_input: RouterInput,
        placed_nodes: Dict[str, PlacedNode],
    ) -> Set[Vc]:
        """Return the voxel footprint of every InlineInstrument placed node.

        These voxels are added to the static ``forbidden`` set before any line
        is routed so that the path-finder cannot thread a pipe through an
        instrument body.
        """
        blocked: Set[Vc] = set()
        for node in router_input.nodes:
            if node.node_type != "InlineInstrument":
                continue
            if node.node_id not in placed_nodes:
                continue
            blocked.add(placed_nodes[node.node_id].vc)
        return blocked

    @staticmethod
    def _infer_custom_center_wc(
        nodes: List[NodeSpec],
        placed_nodes: Dict[str, PlacedNode],
    ) -> tuple[float, float, float]:
        inferred: List[tuple[float, float, float]] = []
        for node in nodes:
            local = node.properties.get("port_local_wc")
            if not (isinstance(local, list) and len(local) == 3):
                continue
            px, py, pz = placed_nodes[node.node_id].wc
            inferred.append((px - float(local[0]), py - float(local[1]), pz - float(local[2])))
        if inferred:
            n = float(len(inferred))
            return (
                sum(v[0] for v in inferred) / n,
                sum(v[1] for v in inferred) / n,
                sum(v[2] for v in inferred) / n,
            )
        n = float(len(nodes))
        return (
            sum(placed_nodes[nn.node_id].wc[0] for nn in nodes) / n,
            sum(placed_nodes[nn.node_id].wc[1] for nn in nodes) / n,
            sum(placed_nodes[nn.node_id].wc[2] for nn in nodes) / n,
        )

    @staticmethod
    def _infer_custom_extent(nodes: List[NodeSpec]) -> tuple[int, int, int]:
        for node in nodes:
            raw = node.properties.get("module_voxel_extent")
            if isinstance(raw, list) and len(raw) == 3:
                return (max(1, int(raw[0])), max(1, int(raw[1])), max(1, int(raw[2])))
        return (3, 2, 2)

    @staticmethod
    def _wc_to_vc(wc: tuple[float, float, float], config: RouterConfig) -> Vc:
        """Convert world coordinates to voxel coordinates using config voxel_size."""
        vs = config.voxel_size
        vx = int(round(wc[0] / vs - 0.5))
        vy = int(round(wc[1] / vs - 0.5))
        vz = int(round(wc[2] / vs - 0.5))
        return (vx, vy, vz)

    def _dilate_path(self, path: Iterable[Vc], margin: int) -> Set[Vc]:
        if margin <= 0:
            return set(path)
        expanded: Set[Vc] = set()
        for x, y, z in path:
            for dx in range(-margin, margin + 1):
                for dy in range(-margin, margin + 1):
                    for dz in range(-margin, margin + 1):
                        expanded.add((x + dx, y + dy, z + dz))
        return expanded
