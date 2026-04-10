from __future__ import annotations

from typing import Dict, Protocol

from .config import RouterConfig
from .RouterInputModels import RouterInput
from .domain_types import LineRouteMap, PlacedNodeMap


class IJsonEmitter(Protocol):
    """Emits generation-layer JSON from placed nodes and per-line voxel routes."""

    def emit(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
        config: RouterConfig,
    ) -> Dict[str, object]:
        ...
