from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from ..config import RouterConfig
from ..emission.minimal_emitter import MinimalJsonEmitter
from ..grid.grid import Grid3D
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
    """Default end-to-end router pipeline service."""

    config: RouterConfig = field(default_factory=RouterConfig)
    parser: RouterInputParser = field(default_factory=RouterInputParser)
    node_placer: NodePlacer = field(default_factory=SimpleNodePlacer)
    path_finder: PathFinder = field(default_factory=ClearanceAwareShortestPathFinder)
    multi_line_router: MultiLineRouter = field(default_factory=SequentialMultiLineRouter)
    json_emitter: object = field(default_factory=MinimalJsonEmitter)
    shell_snapper: EquipmentPortShellSnapper = field(default_factory=EquipmentPortShellSnapper)

    def route(self, router_input: Dict[str, object]) -> Dict[str, object]:
        typed_input = self.parser.parse(router_input)
        placed_nodes = self.node_placer.place_nodes(typed_input, self.config)
        self.shell_snapper.apply(typed_input, placed_nodes, self.config)
        nx, ny, nz = self.config.grid_dimensions
        grid = Grid3D(nx=nx, ny=ny, nz=nz, occupied=set())
        line_routes = self.multi_line_router.route_all_lines(
            grid=grid,
            placed_nodes=placed_nodes,
            router_input=typed_input,
            path_finder=self.path_finder,
            config=self.config,
        )
        generation_json = self.json_emitter.emit(
            router_input=typed_input,
            placed_nodes=placed_nodes,
            line_routes=line_routes,
            config=self.config,
        )
        return generation_json
