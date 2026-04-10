from __future__ import annotations

from typing import Dict, Protocol

from .RouterInputModels import RouterInput
from .config import RouterConfig
from .domain_types import LineRouteMap, PlacedNode
from .grid import Grid3D
from .IPathFinder import IPathFinder


class IMultiLineRouter(Protocol):
    """Multi-line routing strategy interface."""

    def route_all_lines(
        self,
        grid: Grid3D,
        placed_nodes: Dict[str, PlacedNode],
        router_input: RouterInput,
        path_finder: IPathFinder,
        config: RouterConfig,
    ) -> LineRouteMap:
        ...
