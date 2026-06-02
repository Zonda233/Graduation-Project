from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Literal, Optional, Tuple

if TYPE_CHECKING:
    # Avoid a circular import at runtime; RoutingRule only needed for type hints.
    from .routing.routing_rule import RoutingRule


@dataclass
class RouterConfig:
    """
    Basic configuration for the routing layer.

    This is intentionally small; more fields can be added later as needed.
    """

    # Voxel grid configuration (aligned with generation-layer meta.voxel_grid)
    voxel_size: float = 0.2
    grid_dimensions: Tuple[int, int, int] = (20, 20, 20)
    origin_wc: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    # Multi-line routing strategy (P3). Only sequential is implemented for now.
    multi_line_strategy: Literal["sequential", "cbs", "pbs"] = "sequential"

    # Whether to expand already routed paths into a safety margin (in voxels)
    safety_margin_voxels: int = 0

    # Geometry fitting parameters used when converting routed paths to components.
    # Keep consistent with generation-layer defaults for robust mesh stitching.
    elbow_overlap_m: float = 0.003
    tee_run_half_length_factor: float = 1.5
    tee_branch_half_length_factor: float = 1.25

    # Injectable routing rules (Step 4 scaffold).
    # Each rule's apply_to_grid() is called once before routing begins.
    # Each rule's score_path() is reserved for future soft-constraint scoring.
    # Default is an empty list (no extra rules beyond the hardcoded invariants).
    rules: List["RoutingRule"] = field(default_factory=list)

    # Tank geometry — must match GeometryHelper.SHELL_RADIUS so that shell-nozzle
    # placement in SimpleNodePlacer produces flush pipe connections.
    shell_radius: float = 0.3

    # Node-placer overrides for retry attempts.
    # When set, DefaultRouterService uses these values instead of the values
    # from router_input.constraints.spatial_rules.  This lets the router-side
    # retry loop increase spacing without touching the VLM output.
    # None means "use whatever the router_input says" (default behaviour).
    placer_clearance_voxels: Optional[int] = None
    placer_search_radius_voxels: Optional[int] = None

