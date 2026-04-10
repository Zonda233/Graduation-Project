from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .ClearanceAwareShortestPathFinder import ClearanceAwareShortestPathFinder
from .INodePlacer import INodePlacer
from .IPathFinder import IPathFinder
from .IRouterService import IRouterService
from .MapfMultiLineRouter import MapfMultiLineRouter
from .RouterInputParser import RouterInputParser
from .config import RouterConfig
from .json_emitter import JsonEmitter, MinimalJsonEmitter
from .node_placer import SimpleNodePlacer


@dataclass
class MapfRouterService(IRouterService):
    """Placeholder service for future MAPF backend."""

    config: RouterConfig = field(default_factory=lambda: RouterConfig(multi_line_strategy="cbs"))
    parser: RouterInputParser = field(default_factory=RouterInputParser)
    node_placer: INodePlacer = field(default_factory=SimpleNodePlacer)
    path_finder: IPathFinder = field(default_factory=ClearanceAwareShortestPathFinder)
    multi_line_router: MapfMultiLineRouter = field(default_factory=MapfMultiLineRouter)
    json_emitter: JsonEmitter = field(default_factory=MinimalJsonEmitter)

    def route(self, router_input: Dict[str, object]) -> Dict[str, object]:
        raise NotImplementedError("MapfRouterService is not implemented yet.")
