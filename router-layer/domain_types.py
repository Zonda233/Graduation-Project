from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


Vc = Tuple[int, int, int]
Wc = Tuple[float, float, float]


@dataclass
class PlacedNode:
    node_id: str
    wc: Wc
    vc: Vc
    direction: Optional[str] = None  # e.g. "-Z" for tank outlet; first/last pipe step must match


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


PlacedNodeMap = Dict[str, PlacedNode]
LineRouteMap = Dict[str, LineRouteResult]
