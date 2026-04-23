"""
Router layer package.

Public entrypoint: `DefaultRouterService.route(router_input: dict) -> dict`
"""

from .config import RouterConfig
from .service.default_service import DefaultRouterService
from .service.router_service import RouterService

__all__ = [
    "RouterService",
    "DefaultRouterService",
    "RouterConfig",
]
