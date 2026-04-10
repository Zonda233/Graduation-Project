from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set, Tuple

Vc = Tuple[int, int, int]


@dataclass
class Grid3D:
    """
    Minimal 3D grid abstraction for pathfinding.

    Internally this is a very simple boolean occupancy grid (True = free, False = blocked).
    This is enough for the initial sequential A* implementation, and can later be
    replaced or backed by numpy, dijkstra3d, or other libraries without changing
    the public interface.
    """

    nx: int
    ny: int
    nz: int
    occupied: Set[Vc]

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.nx, self.ny, self.nz

    def in_bounds(self, vc: Vc) -> bool:
        x, y, z = vc
        return 0 <= x < self.nx and 0 <= y < self.ny and 0 <= z < self.nz

    def is_free(self, vc: Vc) -> bool:
        return self.in_bounds(vc) and vc not in self.occupied

    def with_forbidden(self, forbidden: Iterable[Vc]) -> "Grid3D":
        """
        Return a shallow copy with additional forbidden voxels.
        """
        new_occupied = set(self.occupied)
        new_occupied.update(forbidden)
        return Grid3D(self.nx, self.ny, self.nz, new_occupied)

    def with_allowed(self, allowed: Iterable[Vc]) -> "Grid3D":
        """
        Return a shallow copy with selected voxels unblocked.
        """
        new_occupied = set(self.occupied)
        for vc in allowed:
            new_occupied.discard(vc)
        return Grid3D(self.nx, self.ny, self.nz, new_occupied)

