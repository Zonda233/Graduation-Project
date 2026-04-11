from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .ClearanceAwareShortestPathFinder import ClearanceAwareShortestPathFinder
from .EquipmentPortShellSnapper import EquipmentPortShellSnapper
from .INodePlacer import INodePlacer
from .IPathFinder import IPathFinder
from .IRouterService import IRouterService
from .IMultiLineRouter import IMultiLineRouter
from .RouterInputParser import RouterInputParser
from .config import RouterConfig
from .grid import Grid3D
from .json_emitter import JsonEmitter, MinimalJsonEmitter
from .node_placer import SimpleNodePlacer
from .SequentialMultiLineRouter import SequentialMultiLineRouter


@dataclass
class DefaultRouterService(IRouterService):
    """Default end-to-end router pipeline service."""

    config: RouterConfig = field(default_factory=RouterConfig)
    parser: RouterInputParser = field(default_factory=RouterInputParser)
    node_placer: INodePlacer = field(default_factory=SimpleNodePlacer)
    path_finder: IPathFinder = field(default_factory=ClearanceAwareShortestPathFinder)
    multi_line_router: IMultiLineRouter = field(default_factory=SequentialMultiLineRouter)
    json_emitter: JsonEmitter = field(default_factory=MinimalJsonEmitter)
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
