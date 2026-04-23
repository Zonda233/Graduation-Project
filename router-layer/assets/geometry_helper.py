from __future__ import annotations

from dataclasses import dataclass

from ..config import RouterConfig
from ..models.domain_types import PlacedNode
from ..models.input_models import NodeSpec


@dataclass
class EquipmentPortInfo:
    """Carries port-related information for asset building."""
    port_id: str
    placed_node: PlacedNode
    node_spec: NodeSpec


class GeometryHelper:
    """World-coordinate ↔ voxel-coordinate conversion and tank geometry helpers."""

    SHELL_RADIUS = 0.3
    SHELL_HEIGHT = 0.5
    HEAD_RATIO = 0.25
    HEAD_HEIGHT = SHELL_RADIUS * HEAD_RATIO
    VOXEL_ORIGIN_OFFSET = [-2, -2, -3]
    VOXEL_EXTENT = [4, 4, 6]

    def __init__(self, config: RouterConfig) -> None:
        self.origin_wc = config.origin_wc
        self.voxel_size = config.voxel_size

    def world_to_voxel(self, wc: list[float]) -> tuple[int, int, int]:
        ox, oy, oz = self.origin_wc
        vs = self.voxel_size
        vx = int(round((wc[0] - ox) / vs - 0.5))
        vy = int(round((wc[1] - oy) / vs - 0.5))
        vz = int(round((wc[2] - oz) / vs - 0.5))
        return vx, vy, vz

    def compute_tank_wc_center(self, base_wc: list[float]) -> list[float]:
        return [
            base_wc[0],
            base_wc[1],
            base_wc[2] + self.SHELL_HEIGHT / 2.0 + self.HEAD_HEIGHT,
        ]

    def compute_voxel_origin_and_extent(
        self, center_voxel: tuple[int, int, int]
    ) -> tuple[list[int], list[int]]:
        cx, cy, cz = center_voxel
        origin = [
            cx + self.VOXEL_ORIGIN_OFFSET[0],
            cy + self.VOXEL_ORIGIN_OFFSET[1],
            max(0, cz + self.VOXEL_ORIGIN_OFFSET[2]),
        ]
        extent = self.VOXEL_EXTENT.copy()
        return origin, extent
