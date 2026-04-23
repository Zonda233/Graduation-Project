from __future__ import annotations

from typing import Iterable, List, Optional, Protocol

from ..grid.grid import Grid3D
from ..models.input_models import LineSpec
from ..models.types import Vc


class PathFinder(Protocol):
    """Pathfinder strategy interface."""

    def find_path(
        self,
        grid: Grid3D,
        start_vc: Vc,
        goal_vc: Vc,
        via_vc: Optional[List[Vc]] = None,
        forbidden: Optional[Iterable[Vc]] = None,
        line_ctx: Optional[LineSpec] = None,
        start_direction: Optional[str] = None,
        end_direction: Optional[str] = None,
    ) -> List[Vc]:
        ...
