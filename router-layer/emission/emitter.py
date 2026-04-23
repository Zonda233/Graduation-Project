from __future__ import annotations

from typing import Dict, Protocol, runtime_checkable

from ..config import RouterConfig
from ..models.domain_types import LineRouteMap, PlacedNodeMap
from ..models.input_models import RouterInput


@runtime_checkable
class JsonEmitter(Protocol):
    """Emits generation-layer JSON from placed nodes and per-line voxel routes."""

    def emit(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
        config: RouterConfig,
    ) -> Dict[str, object]: ...
