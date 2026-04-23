from __future__ import annotations

from typing import Dict, Protocol

from ..models.domain_types import PlacedNode
from ..models.input_models import RouterInput
from ..config import RouterConfig


class NodePlacer(Protocol):
    """Node placement strategy interface."""

    def place_nodes(self, router_input: RouterInput, config: RouterConfig) -> Dict[str, PlacedNode]:
        ...
