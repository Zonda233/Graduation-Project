from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import RouterConfig
from ..emission.minimal_emitter import MinimalJsonEmitter
from ..grid.grid import Grid3D
from ..models.domain_types import RouteResult, RoutingFailure
from ..parsing.input_parser import RouterInputParser
from ..pathfinding.clearance_path_finder import ClearanceAwareShortestPathFinder
from ..pathfinding.path_finder import PathFinder
from ..placement.node_placer import NodePlacer
from ..placement.simple_node_placer import SimpleNodePlacer
from ..routing.multi_line_router import MultiLineRouter
from ..routing.sequential_router import SequentialMultiLineRouter
from ..snapping.shell_snapper import EquipmentPortShellSnapper


@dataclass
class DefaultRouterService:
    """Default end-to-end router pipeline service.

    Returns a RouteResult rather than raising on routing failure so that
    callers (test harness, VLM retry loop) can inspect the full diagnostic.
    """

    config: RouterConfig = field(default_factory=RouterConfig)
    parser: RouterInputParser = field(default_factory=RouterInputParser)
    node_placer: NodePlacer = field(default_factory=SimpleNodePlacer)
    path_finder: PathFinder = field(default_factory=ClearanceAwareShortestPathFinder)
    multi_line_router: MultiLineRouter = field(default_factory=SequentialMultiLineRouter)
    json_emitter: object = field(default_factory=MinimalJsonEmitter)
    shell_snapper: EquipmentPortShellSnapper = field(default_factory=EquipmentPortShellSnapper)

    def route(self, router_input: Dict[str, object]) -> RouteResult:
        """Run the full routing pipeline and return a RouteResult.

        On success:  RouteResult(success=True, output_json=..., failures=[])
        On failure:  RouteResult(success=False, output_json=None,
                                 failures=[...], failure_report=...)

        If ``self.config.placer_clearance_voxels`` or
        ``self.config.placer_search_radius_voxels`` are set, they override the
        corresponding values from ``router_input.constraints.spatial_rules``
        before node placement.  This allows the router-side retry loop to
        increase node spacing without modifying the VLM output.
        """
        typed_input = self.parser.parse(router_input)

        # Apply config-level placer overrides (used by router-side retry loop).
        # We deep-copy the constraints so the original router_input dict is
        # never mutated between retry attempts.
        if (
            self.config.placer_clearance_voxels is not None
            or self.config.placer_search_radius_voxels is not None
        ):
            typed_input = copy.copy(typed_input)
            typed_input.constraints = copy.copy(typed_input.constraints)
            typed_input.constraints.spatial_rules = copy.copy(
                typed_input.constraints.spatial_rules
            )
            if self.config.placer_clearance_voxels is not None:
                typed_input.constraints.spatial_rules.default_clearance_voxels = (
                    self.config.placer_clearance_voxels
                )
            if self.config.placer_search_radius_voxels is not None:
                typed_input.constraints.spatial_rules.max_search_radius_voxels = (
                    self.config.placer_search_radius_voxels
                )

        placed_nodes = self.node_placer.place_nodes(typed_input, self.config)
        self.shell_snapper.apply(typed_input, placed_nodes, self.config)

        nx, ny, nz = self.config.grid_dimensions
        grid = Grid3D(nx=nx, ny=ny, nz=nz, occupied=set(), voxel_size=self.config.voxel_size)

        line_routes = self.multi_line_router.route_all_lines(
            grid=grid,
            placed_nodes=placed_nodes,
            router_input=typed_input,
            path_finder=self.path_finder,
            config=self.config,
        )

        # Collect failures (I-5: routing failure is never silent).
        failures: List[RoutingFailure] = []
        for result in line_routes.values():
            if not result.success and result.failure is not None:
                failures.append(result.failure)
            elif not result.success:
                # Fallback for routers that don't populate result.failure.
                from ..models.domain_types import RoutingFailure as RF
                failures.append(RF(
                    line_id=result.line_id,
                    reason=result.reason or "no_path_found",
                    start_vc=(0, 0, 0),
                    goal_vc=(0, 0, 0),
                ))

        if failures:
            report_lines = [
                f"=== ROUTING FAILURES ({len(failures)} line(s)) ===",
            ]
            for f in failures:
                report_lines.append(f.message)
            failure_report = "\n\n".join(report_lines)
            return RouteResult(
                success=False,
                output_json=None,
                failures=failures,
                failure_report=failure_report,
            )

        generation_json = self.json_emitter.emit(
            router_input=typed_input,
            placed_nodes=placed_nodes,
            line_routes=line_routes,
            config=self.config,
        )
        return RouteResult(
            success=True,
            output_json=generation_json,
            failures=[],
            failure_report=None,
        )
