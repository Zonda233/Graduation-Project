from __future__ import annotations

from typing import Dict, Protocol

from .RouterInputModels import RouterInput
from .config import RouterConfig
from .domain_types import PlacedNode


class INodePlacer(Protocol):
    """Node placement strategy interface."""

    def place_nodes(self, router_input: RouterInput, config: RouterConfig) -> Dict[str, PlacedNode]:
        ...
