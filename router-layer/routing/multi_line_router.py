from __future__ import annotations

from typing import Dict, runtime_checkable

from typing import Protocol

from ..config import RouterConfig
from ..grid.grid import Grid3D
from ..models.domain_types import LineRouteMap, PlacedNode
from ..models.input_models import RouterInput
from ..pathfinding.path_finder import PathFinder


@runtime_checkable
class MultiLineRouter(Protocol):
    """Multi-line routing strategy interface."""

    def route_all_lines(
        self,
        grid: Grid3D,
        placed_nodes: Dict[str, PlacedNode],
        router_input: RouterInput,
        path_finder: PathFinder,
        config: RouterConfig,
    ) -> LineRouteMap: ...
