"""VLM-layer perception sub-package: P&ID image parsing via VLM."""

from .pid_parser import generate_router_input_from_image

__all__ = ["generate_router_input_from_image"]
