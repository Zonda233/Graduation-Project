from __future__ import annotations

from typing import Dict

from .IJsonEmitter import IJsonEmitter
from .RouterInputModels import RouterInput
from .config import RouterConfig
from .domain_types import LineRouteMap, PlacedNodeMap


class FullJsonEmitter(IJsonEmitter):
    """Placeholder for a full emitter matching chemical-piping-lib Final_JSON (valves, reducers, caps, …)."""

    def emit(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
        config: RouterConfig,
    ) -> Dict[str, object]:
        raise NotImplementedError("FullJsonEmitter is not implemented yet.")
