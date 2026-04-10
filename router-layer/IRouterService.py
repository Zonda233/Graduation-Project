from __future__ import annotations

from typing import Dict, Protocol


class IRouterService(Protocol):
    """Router service interface."""

    def route(self, router_input: Dict[str, object]) -> Dict[str, object]:
        ...
