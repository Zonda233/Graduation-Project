from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from ..config import RouterConfig
from ..grid.grid import Grid3D
from ..grid.occupancy_grid import OccupancyGrid
from ..models.domain_types import LineRouteMap, LineRouteResult, PlacedNode, RoutingFailure
from ..models.input_models import NodeSpec, RouterInput
from ..models.types import Vc
from ..pathfinding.path_finder import PathFinder


@dataclass
class SequentialMultiLineRouter:
    """Routes lines sequentially using a unified OccupancyGrid.

    Invariants enforced here (see router-layer-refactor-v2.md §1):

    I-2  All equipment bodies are in static_occupied before routing begins.
    I-3  Port voxels are in static_occupied; route_context() frees only the
         two endpoints for each individual find_path call.
    I-6  block_path() excludes all_port_vcs so port/junction voxels are
         never permanently blocked by a previously routed path.
    """

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

        # ------------------------------------------------------------------
        # Build OccupancyGrid (I-2, I-3)
        # ------------------------------------------------------------------
        # Collect all port/junction voxels across every line — these must
        # never be permanently blocked by block_path().
        all_port_vcs: Set[Vc] = set()
        for line in router_input.lines:
            all_port_vcs.add(placed_nodes[line.from_node_id].vc)
            all_port_vcs.add(placed_nodes[line.to_node_id].vc)
            for nid in line.via_node_ids:
                all_port_vcs.add(placed_nodes[nid].vc)

        # Build static_occupied: all equipment body voxels INCLUDING port voxels.
        static_occupied: Set[Vc] = set()
        static_occupied |= self._custom_module_blocked_voxels(
            router_input, placed_nodes, config
        )
        static_occupied |= self._instrument_blocked_voxels(router_input, placed_nodes)
        static_occupied |= self._reducer_blocked_voxels(router_input, placed_nodes)
        # Port voxels of custom-module ports are already inside the bounding
        # box computed above.  For InlineInstrument the single voxel IS the
        # port.  Both are therefore already in static_occupied — no extra step
        # needed.  (Tank ports are not currently blocked because Tank bodies
        # are not yet added to static_occupied; that is a future extension.)

        occ = OccupancyGrid(
            nx=grid.nx,
            ny=grid.ny,
            nz=grid.nz,
            voxel_size=grid.voxel_size,
            static_occupied=frozenset(static_occupied),
            dynamic_occupied=set(),
            all_port_vcs=frozenset(all_port_vcs),
        )

        # ------------------------------------------------------------------
        # Apply injectable rules (Step 4 — apply_to_grid phase)
        # Each rule may add voxels to static_occupied or dynamic_occupied.
        # Rules must not remove voxels from static_occupied.
        # ------------------------------------------------------------------
        for rule in config.rules:
            occ = rule.apply_to_grid(occ, router_input, placed_nodes)

        # ------------------------------------------------------------------
        # Sequential routing
        # ------------------------------------------------------------------
        for line in router_input.lines:
            line_id = line.line_id
            start_placed = placed_nodes[line.from_node_id]
            goal_placed = placed_nodes[line.to_node_id]
            goal_node = node_by_id.get(line.to_node_id)

            end_direction = goal_placed.direction
            if goal_node and self._is_custom_module_port(goal_node) and end_direction:
                end_direction = self._opposite_axis(end_direction)

            via_vc: List[Vc] = [placed_nodes[nid].vc for nid in line.via_node_ids]

            # I-3: temporarily free start and goal voxels for this find_path call.
            ctx = occ.route_context(start_placed.vc, goal_placed.vc)

            path = path_finder.find_path(
                grid=ctx,
                start_vc=start_placed.vc,
                goal_vc=goal_placed.vc,
                via_vc=via_vc or None,
                forbidden=None,          # occupancy is fully encoded in ctx
                line_ctx=line,
                start_direction=start_placed.direction,
                end_direction=end_direction,
            )

            if not path:
                # Build diagnostic snapshot for VLM retry (I-5).
                failure = self._build_failure(
                    line_id=line_id,
                    reason="no_path_found",
                    start_vc=start_placed.vc,
                    goal_vc=goal_placed.vc,
                    start_direction=start_placed.direction,
                    end_direction=end_direction,
                    occ=ctx,
                    routed_before=[
                        lid for lid, r in results.items() if r.success
                    ],
                )
                results[line_id] = LineRouteResult(
                    line_id=line_id,
                    voxel_path=None,
                    success=False,
                    reason="no_path_found",
                    failure=failure,
                )
                continue

            results[line_id] = LineRouteResult(
                line_id=line_id,
                voxel_path=path,
                success=True,
                reason=None,
            )
            # I-6: block the routed path for subsequent lines, excluding port voxels.
            occ.block_path(path, config.safety_margin_voxels)

        return results

    # ------------------------------------------------------------------
    # Failure diagnostic builder (I-5)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_failure(
        line_id: str,
        reason: str,
        start_vc: Vc,
        goal_vc: Vc,
        start_direction: Optional[str],
        end_direction: Optional[str],
        occ: OccupancyGrid,
        routed_before: List[str],
    ) -> RoutingFailure:
        """Collect occupied voxels within 2 steps of start/goal for diagnosis."""
        def _neighbours_2(vc: Vc) -> List[Vc]:
            x, y, z = vc
            result = []
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    for dz in range(-2, 3):
                        if dx == 0 and dy == 0 and dz == 0:
                            continue
                        result.append((x + dx, y + dy, z + dz))
            return result

        near_start = [v for v in _neighbours_2(start_vc) if not occ.is_free(v)]
        near_goal = [v for v in _neighbours_2(goal_vc) if not occ.is_free(v)]

        return RoutingFailure(
            line_id=line_id,
            reason=reason,
            start_vc=start_vc,
            goal_vc=goal_vc,
            start_direction=start_direction,
            end_direction=end_direction,
            forbidden_near_start=near_start,
            forbidden_near_goal=near_goal,
            routed_before=routed_before,
        )

    # ------------------------------------------------------------------
    # Equipment occupancy helpers
    # ------------------------------------------------------------------

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
        """Return all voxels inside every CustomModule bounding box.

        Port voxels are included (they are inside the bounding box).
        route_context() will free them per-line as needed.
        """
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
        """Return the single voxel footprint of every InlineInstrument.

        The instrument voxel is both the body and the port; it is added to
        static_occupied and freed per-line via route_context() when a line
        connects to this instrument.
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
    def _reducer_blocked_voxels(
        router_input: RouterInput,
        placed_nodes: Dict[str, PlacedNode],
    ) -> Set[Vc]:
        """Return the single voxel footprint of every InlineReducer.

        Like InlineInstrument, the reducer occupies exactly one voxel on the
        pipe path.  It is added to static_occupied so that other lines cannot
        route through it, and freed per-line via route_context() when a line
        that passes through this reducer is being routed.
        """
        blocked: Set[Vc] = set()
        for node in router_input.nodes:
            if node.node_type != "InlineReducer":
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
            inferred.append((
                px - float(local[0]),
                py - float(local[1]),
                pz - float(local[2]),
            ))
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
        """Convert world coordinates to voxel coordinates using floor(wc / voxel_size)."""
        vs = config.voxel_size
        return (
            math.floor(wc[0] / vs),
            math.floor(wc[1] / vs),
            math.floor(wc[2] / vs),
        )
