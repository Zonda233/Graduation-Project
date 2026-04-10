from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PlacementHint:
    z_layers: List[int] = field(default_factory=list)
    anchor_policy: Optional[str] = None
    direction_preferred: Optional[str] = None


@dataclass
class BBoxHint:
    extent_voxels: List[int] = field(default_factory=list)
    clearance_voxels: Optional[int] = None


@dataclass
class SpatialRules:
    default_clearance_voxels: int = 0
    max_search_radius_voxels: int = 4
    default_z_layers: List[int] = field(default_factory=lambda: [0])


@dataclass
class NodeSpec:
    node_id: str
    node_type: str
    role: Optional[str] = None
    label: Optional[str] = None
    pid_tag: Optional[str] = None
    equipment_ref: Optional[str] = None
    location_2d_x: Optional[float] = None
    location_2d_y: Optional[float] = None
    placement_hint: PlacementHint = field(default_factory=PlacementHint)
    bbox_hint: BBoxHint = field(default_factory=BBoxHint)


@dataclass
class LineSpec:
    line_id: str
    tag: Optional[str]
    from_node_id: str
    to_node_id: str
    via_node_ids: List[str] = field(default_factory=list)
    nominal_diameter_mm: Optional[float] = None
    with_flanges: bool = False
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass
class ConstraintsSpec:
    spatial_rules: SpatialRules = field(default_factory=SpatialRules)


@dataclass
class RouterInput:
    meta: Dict[str, object]
    nodes: List[NodeSpec]
    lines: List[LineSpec]
    constraints: ConstraintsSpec = field(default_factory=ConstraintsSpec)
    raw: Dict[str, object] = field(default_factory=dict)
