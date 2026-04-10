"""
Router layer package.

This package implements a minimal, sequential A* based routing layer that:
- Consumes router-input-protocol JSON (graph-level).
- Emits generation-layer JSON compatible (in shape) with chemical-piping-lib.

The public entrypoint for callers is `DefaultRouterService.route(router_input: dict) -> dict`.
"""

from .config import RouterConfig
from .service import DefaultRouterService, IRouterService

__all__ = [
    "IRouterService",
    "DefaultRouterService",
    "RouterConfig",
]

