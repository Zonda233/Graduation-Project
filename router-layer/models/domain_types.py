from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .types import Vc, Wc


@dataclass
class PlacedNode:
    node_id: str
    wc: Wc
    vc: Vc
    direction: Optional[str] = None  # e.g. "-Z" for tank outlet


@dataclass
class VoxelPath:
    line_id: str
    ordered_vc: List[Vc]


@dataclass
class LineRouteResult:
    line_id: str
    voxel_path: Optional[List[Vc]]
    success: bool
    reason: Optional[str] = None
    failure: Optional["RoutingFailure"] = None


@dataclass
class RoutingFailure:
    """Structured failure record for a single line that could not be routed.

    The ``message`` field is formatted for direct inclusion in a VLM retry
    prompt (see router-layer-refactor-v2.md §4.2).
    """

    line_id: str
    reason: str                           # "no_path_found" | "direction_blocked" | ...
    start_vc: Vc
    goal_vc: Vc
    start_direction: Optional[str] = None
    end_direction: Optional[str] = None
    forbidden_near_start: List[Vc] = field(default_factory=list)
    forbidden_near_goal: List[Vc] = field(default_factory=list)
    routed_before: List[str] = field(default_factory=list)
    message: str = ""                     # human-readable summary for VLM retry

    def __post_init__(self) -> None:
        if not self.message:
            self.message = self._build_message()

    def _build_message(self) -> str:
        lines = [
            f"Line '{self.line_id}' could not be routed.",
            f"  Start vc: {self.start_vc}"
            + (f", direction={self.start_direction!r}" if self.start_direction else ""),
            f"  Goal  vc: {self.goal_vc}"
            + (f", direction={self.end_direction!r}" if self.end_direction else ""),
            f"  Reason: {self.reason}",
        ]
        if self.forbidden_near_start:
            lines.append(f"  Occupied voxels near start: {self.forbidden_near_start}")
        if self.forbidden_near_goal:
            lines.append(f"  Occupied voxels near goal:  {self.forbidden_near_goal}")
        if self.routed_before:
            lines.append(f"  Lines already routed: {self.routed_before}")
        lines.append(
            "  Suggestion: increase safety_margin_voxels, change routing order,"
            " or adjust node positions."
        )
        return "\n".join(lines)


@dataclass
class RouteResult:
    """Return type of the router service.

    On full success ``success=True``, ``output_json`` is populated, and
    ``failures`` is empty.  On any routing failure ``success=False``,
    ``output_json`` is None, and ``failure_report`` contains a formatted
    message suitable for a VLM retry prompt.
    """

    success: bool
    output_json: Optional[Dict]           # None if any line failed
    failures: List[RoutingFailure] = field(default_factory=list)
    failure_report: Optional[str] = None  # formatted message for VLM, None on success


PlacedNodeMap = Dict[str, PlacedNode]
LineRouteMap = Dict[str, LineRouteResult]
