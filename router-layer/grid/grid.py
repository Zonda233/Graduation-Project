from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set, Tuple

from ..models.types import Vc


@dataclass
class Grid3D:
    """Minimal 3D boolean occupancy grid for pathfinding."""

    nx: int
    ny: int
    nz: int
    occupied: Set[Vc]
    voxel_size: float = 0.2  # metres per voxel edge; used by elbow-spacing constraint

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.nx, self.ny, self.nz

    def in_bounds(self, vc: Vc) -> bool:
        x, y, z = vc
        return 0 <= x < self.nx and 0 <= y < self.ny and 0 <= z < self.nz

    def is_free(self, vc: Vc) -> bool:
        return self.in_bounds(vc) and vc not in self.occupied

    def with_forbidden(self, forbidden: Iterable[Vc]) -> "Grid3D":
        new_occupied = set(self.occupied)
        new_occupied.update(forbidden)
        return Grid3D(self.nx, self.ny, self.nz, new_occupied, self.voxel_size)

    def with_allowed(self, allowed: Iterable[Vc]) -> "Grid3D":
        new_occupied = set(self.occupied)
        for vc in allowed:
            new_occupied.discard(vc)
        return Grid3D(self.nx, self.ny, self.nz, new_occupied, self.voxel_size)
