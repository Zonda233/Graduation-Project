from __future__ import annotations

from typing import Dict, Protocol, runtime_checkable


@runtime_checkable
class RouterService(Protocol):
    """End-to-end router pipeline interface."""

    def route(self, router_input: Dict[str, object]) -> Dict[str, object]: ...
