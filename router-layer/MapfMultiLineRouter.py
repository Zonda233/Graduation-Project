from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .IMultiLineRouter import IMultiLineRouter
from .RouterInputModels import RouterInput
from .config import RouterConfig
from .domain_types import LineRouteMap, PlacedNode
from .grid import Grid3D
from .IPathFinder import IPathFinder


@dataclass
class MapfMultiLineRouter(IMultiLineRouter):
    """Placeholder for future MAPF backend (CBS/PBS)."""

    backend: str = "w9_cbs"

    def route_all_lines(
        self,
        grid: Grid3D,
        placed_nodes: Dict[str, PlacedNode],
        router_input: RouterInput,
        path_finder: IPathFinder,
        config: RouterConfig,
    ) -> LineRouteMap:
        raise NotImplementedError("MapfMultiLineRouter is not implemented yet.")
