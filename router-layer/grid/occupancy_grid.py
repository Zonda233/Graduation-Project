from __future__ import annotations

"""
OccupancyGrid
=============

Unified occupancy model for the sequential router.

Invariants (see _generated_docs/router-layer-refactor-v2.md §1):

I-1  A voxel is either occupied or free — no "allowed" exemption sets.
I-2  All equipment bodies (Tank, CustomModule, InlineInstrument) are in
     static_occupied before the first find_path call.
I-3  Port voxels are also in static_occupied.  The ONLY exception: when
     routing a specific line, route_context(start_vc, goal_vc) returns a
     temporary view with those two endpoint voxels freed for that single
     find_path call.
I-6  block_path() excludes all_port_vcs so port/junction voxels are never
     permanently blocked by a previously routed path.
"""

from dataclasses import dataclass, field
from typing import Iterable, List, Set

from ..models.types import Vc


def _dilate(path: Iterable[Vc], margin: int) -> Set[Vc]:
    """Return path voxels expanded by a Chebyshev-distance margin."""
    if margin <= 0:
        return set(path)
    expanded: Set[Vc] = set()
    for x, y, z in path:
        for dx in range(-margin, margin + 1):
            for dy in range(-margin, margin + 1):
                for dz in range(-margin, margin + 1):
                    expanded.add((x + dx, y + dy, z + dz))
    return expanded


@dataclass
class OccupancyGrid:
    """Unified 3D occupancy grid for the sequential router.

    Attributes
    ----------
    nx, ny, nz:
        Grid dimensions (voxels).
    voxel_size:
        Metres per voxel edge; forwarded to the path-finder for the
        elbow-spacing constraint.
    static_occupied:
        Frozen set of voxels blocked by equipment bodies (including port
        voxels).  Never modified directly — use route_context() to get a
        temporary view with endpoints freed.
    dynamic_occupied:
        Grows as lines are routed (via block_path).
    all_port_vcs:
        All port and junction voxels across every line.  block_path()
        excludes these so they are never permanently blocked.
    """

    nx: int
    ny: int
    nz: int
    voxel_size: float
    static_occupied: frozenset  # FrozenSet[Vc]
    dynamic_occupied: Set[Vc] = field(default_factory=set)
    all_port_vcs: frozenset = field(default_factory=frozenset)  # FrozenSet[Vc]

    # ------------------------------------------------------------------
    # Core query
    # ------------------------------------------------------------------

    def in_bounds(self, vc: Vc) -> bool:
        x, y, z = vc
        return 0 <= x < self.nx and 0 <= y < self.ny and 0 <= z < self.nz

    def is_free(self, vc: Vc) -> bool:
        return (
            self.in_bounds(vc)
            and vc not in self.static_occupied
            and vc not in self.dynamic_occupied
        )

    # ------------------------------------------------------------------
    # Per-line endpoint lifting (I-3)
    # ------------------------------------------------------------------

    def route_context(self, start_vc: Vc, goal_vc: Vc) -> "OccupancyGrid":
        """Return a temporary view with start_vc and goal_vc freed.

        The original OccupancyGrid is unchanged.  The returned view shares
        the same dynamic_occupied set (mutations via block_path on the
        returned view will be visible on the original — this is intentional
        so that block_path() after routing updates the shared state).
        """
        lifted = frozenset({start_vc, goal_vc}) & self.static_occupied
        new_static = self.static_occupied - lifted
        return OccupancyGrid(
            nx=self.nx,
            ny=self.ny,
            nz=self.nz,
            voxel_size=self.voxel_size,
            static_occupied=new_static,
            dynamic_occupied=self.dynamic_occupied,  # shared reference
            all_port_vcs=self.all_port_vcs,
        )

    # ------------------------------------------------------------------
    # Path blocking (I-6)
    # ------------------------------------------------------------------

    def block_path(self, path: List[Vc], margin: int) -> None:
        """Add dilated path voxels to dynamic_occupied, excluding port voxels.

        Port and junction voxels (all_port_vcs) are never permanently
        blocked so that subsequent lines can still reach them.
        """
        new_blocked = _dilate(path, margin) - self.all_port_vcs
        self.dynamic_occupied.update(new_blocked)

    # ------------------------------------------------------------------
    # Compatibility shim — Grid3D-like interface used by ClearanceAwareShortestPathFinder
    # ------------------------------------------------------------------

    @property
    def occupied(self) -> Set[Vc]:
        """Union of static and dynamic occupied sets (read-only view).

        The path-finder's clearance BFS iterates over grid.occupied to seed
        the multi-source BFS.  Returning the union here keeps the path-finder
        code unchanged.
        """
        return self.static_occupied | self.dynamic_occupied

    @property
    def shape(self):
        return self.nx, self.ny, self.nz
