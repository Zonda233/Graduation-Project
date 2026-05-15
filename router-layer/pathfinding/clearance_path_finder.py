from __future__ import annotations

"""
ClearanceAwareShortestPathFinder
================================

Two-phase optimal pathfinding on a 3D voxel grid:

Phase A – Shortest-path manifold construction
  BFS from start → dist_start; BFS from goal → dist_goal.
  A voxel n is on some shortest path iff dist_start[n] + dist_goal[n] == shortest_len.

Phase B – Clearance maximisation on the shortest-path DAG
  Multi-source BFS from all occupied voxels → clearance(v).
  DP on the DAG maximises (min_clearance, sum_clearance) lexicographically.

  Elbow-spacing constraint
  ------------------------
  When min_straight > 0, consecutive direction changes (elbows) are forbidden
  unless at least min_straight voxels of straight pipe separate them.
  This prevents S-bend arc intersection: two adjacent 90° elbows each consume
  bend_radius of straight pipe on both sides, so the minimum gap between their
  corner voxels is ceil(2 * bend_radius / voxel_size).

Complexity: O(V + E) time and space (V = grid voxels, E = 6-neighbour edges).
"""

import math
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from ..grid.grid import Grid3D
from ..models.input_models import LineSpec
from ..models.types import Vc

# Elbow bend radius = ELBOW_RADIUS_FACTOR * outer_diameter  (matches generation layer)
_ELBOW_RADIUS_FACTOR: float = 1.5

# Approximate OD lookup by nominal diameter in mm → OD in metres
# (mirrors chemical_piping_lib.config.DN_TABLE without importing Blender-side code)
_OD_BY_NOMINAL_MM: Dict[float, float] = {
    15:  0.02134,
    20:  0.02667,
    25:  0.03340,
    32:  0.04216,
    40:  0.04826,
    50:  0.06033,
    65:  0.07315,
    80:  0.08890,
    100: 0.11430,
    125: 0.14130,
    150: 0.16830,
    200: 0.21910,
    250: 0.27305,
    300: 0.32385,
    350: 0.35560,
    400: 0.40640,
    450: 0.45720,
    500: 0.50800,
}


class ClearanceAwareShortestPathFinder:
    """6-neighbour shortest-path finder with clearance-aware tie-break."""

    DELTA_BY_AXIS: Dict[str, Vc] = {
        "+X": (1, 0, 0),
        "-X": (-1, 0, 0),
        "+Y": (0, 1, 0),
        "-Y": (0, -1, 0),
        "+Z": (0, 0, 1),
        "-Z": (0, 0, -1),
    }

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
        if forbidden:
            allowed = {start_vc, goal_vc}
            if via_vc:
                allowed.update(via_vc)
            # Also exempt the forced first-step voxel: if start_direction is set,
            # _segment_with_directions will check grid.is_free(first_step) and
            # return [] immediately if it's blocked.  A previously-routed path may
            # have occupied that voxel, so we must allow it here.
            if start_direction:
                delta = self.DELTA_BY_AXIS.get(start_direction)
                if delta:
                    allowed.add((
                        start_vc[0] + delta[0],
                        start_vc[1] + delta[1],
                        start_vc[2] + delta[2],
                    ))
            # Same logic for the forced last-step voxel (approach to goal).
            if end_direction:
                delta = self.DELTA_BY_AXIS.get(end_direction)
                if delta:
                    allowed.add((
                        goal_vc[0] - delta[0],
                        goal_vc[1] - delta[1],
                        goal_vc[2] - delta[2],
                    ))
            grid = grid.with_forbidden(v for v in forbidden if v not in allowed)

        # Compute minimum straight-run voxels between consecutive elbows.
        # Formula: ceil(2 * ELBOW_RADIUS_FACTOR * OD / voxel_size)
        min_straight = self._min_straight_voxels(line_ctx, grid.voxel_size)

        waypoints: List[Vc] = [start_vc]
        if via_vc:
            waypoints.extend(via_vc)
        waypoints.append(goal_vc)

        full_path: List[Vc] = []
        for i in range(len(waypoints) - 1):
            seg_start, seg_goal = waypoints[i], waypoints[i + 1]
            force_first = start_direction if (i == 0 and start_direction) else None
            force_last = end_direction if (i == len(waypoints) - 2 and end_direction) else None
            segment = self._segment_with_directions(
                grid, seg_start, seg_goal, force_first, force_last, min_straight
            )
            if not segment:
                return []
            full_path.extend(segment[1:] if full_path else segment)
        return full_path

    @staticmethod
    def _min_straight_voxels(
        line_ctx: Optional[LineSpec],
        voxel_size: float,
    ) -> int:
        """Return the minimum number of straight voxels required between two elbows.

        Derived from: ceil(2 * bend_radius / voxel_size)
        where bend_radius = ELBOW_RADIUS_FACTOR * OD.
        Returns 0 when the nominal diameter is unknown (no constraint applied).
        """
        if line_ctx is None or line_ctx.nominal_diameter_mm is None:
            return 0
        nom_mm = float(line_ctx.nominal_diameter_mm)
        # Find closest DN entry (within 20 % tolerance)
        best_od: Optional[float] = None
        best_diff = float("inf")
        for dn_mm, od in _OD_BY_NOMINAL_MM.items():
            diff = abs(dn_mm - nom_mm)
            if diff < best_diff:
                best_diff = diff
                best_od = od
        if best_od is None or voxel_size <= 0:
            return 0
        bend_radius = _ELBOW_RADIUS_FACTOR * best_od
        return math.ceil(2.0 * bend_radius / voxel_size)

    def _segment_with_directions(
        self,
        grid: Grid3D,
        start: Vc,
        goal: Vc,
        force_first: Optional[str],
        force_last: Optional[str],
        min_straight: int = 0,
    ) -> List[Vc]:
        if force_first:
            delta = self.DELTA_BY_AXIS.get(force_first)
            if not delta:
                return self._solve(grid, start, goal, min_straight)
            first_step = (start[0] + delta[0], start[1] + delta[1], start[2] + delta[2])
            if not grid.is_free(first_step):
                return []
            mid = self._solve(grid, first_step, goal, min_straight)
            return [start] + mid if mid else []

        if force_last:
            delta = self.DELTA_BY_AXIS.get(force_last)
            if not delta:
                return self._solve(grid, start, goal, min_straight)
            last_step = (goal[0] - delta[0], goal[1] - delta[1], goal[2] - delta[2])
            if not grid.is_free(last_step):
                return []
            mid = self._solve(grid, start, last_step, min_straight)
            if mid and goal in mid[:-1]:
                constrained = grid.with_forbidden([goal]).with_allowed([start, last_step])
                mid = self._solve(constrained, start, last_step, min_straight)
            return mid + [goal] if mid else []

        return self._solve(grid, start, goal, min_straight)

    @staticmethod
    def _neighbours(vc: Vc) -> List[Vc]:
        x, y, z = vc
        return [
            (x + 1, y, z), (x - 1, y, z),
            (x, y + 1, z), (x, y - 1, z),
            (x, y, z + 1), (x, y, z - 1),
        ]

    def _solve(
        self,
        grid: Grid3D,
        start: Vc,
        goal: Vc,
        min_straight: int = 0,
    ) -> List[Vc]:
        if not grid.is_free(start) or not grid.is_free(goal):
            return []

        dist_start = self._bfs(grid, start)
        shortest_len = dist_start.get(goal)
        if shortest_len is None:
            return []

        dist_goal = self._bfs(grid, goal)
        clearance = self._clearance_field(grid)

        # best_score[v] = (min_clearance_along_path, sum_clearance_along_path)
        best_score: Dict[Vc, Tuple[int, int]] = {
            start: (clearance.get(start, 0), clearance.get(start, 0))
        }
        parent: Dict[Vc, Optional[Vc]] = {start: None}
        # last_turn_step[v] = dist_start value at which the last direction change
        # occurred on the best path to v.  -inf sentinel means "no turn yet".
        last_turn_step: Dict[Vc, int] = {start: -(min_straight + 1)}

        nodes_by_dist: Dict[int, List[Vc]] = {}
        for node, dist in dist_start.items():
            nodes_by_dist.setdefault(dist, []).append(node)

        for step in range(shortest_len):
            for current in nodes_by_dist.get(step, []):
                current_score = best_score.get(current)
                if current_score is None:
                    continue
                current_lts = last_turn_step.get(current, -(min_straight + 1))

                # Direction of the edge that arrived at `current`
                par = parent[current]
                if par is not None:
                    dir_in: Optional[Tuple[int, int, int]] = (
                        current[0] - par[0],
                        current[1] - par[1],
                        current[2] - par[2],
                    )
                else:
                    dir_in = None

                for nb in self._neighbours(current):
                    if not grid.is_free(nb):
                        continue
                    if dist_start.get(nb) != step + 1:
                        continue
                    if dist_goal.get(nb) != shortest_len - (step + 1):
                        continue

                    # Direction of the edge current → nb
                    dir_out: Tuple[int, int, int] = (
                        nb[0] - current[0],
                        nb[1] - current[1],
                        nb[2] - current[2],
                    )

                    # Detect a direction change (turn / elbow)
                    is_turn = (dir_in is not None) and (dir_out != dir_in)

                    if is_turn and min_straight > 0:
                        # Enforce minimum straight-run between consecutive elbows.
                        # step+1 is the dist_start of nb; current_lts is the
                        # dist_start at which the last turn happened.
                        if (step + 1) - current_lts < min_straight:
                            continue  # too close to previous elbow — skip

                    nb_clear = clearance.get(nb, 0)
                    cand_score = (
                        min(current_score[0], nb_clear),
                        current_score[1] + nb_clear,
                    )
                    nb_lts = (step + 1) if is_turn else current_lts

                    # Accept if no path to nb yet, or if this path scores better,
                    # or if same score but last_turn_step is further back (more
                    # room for future elbows).
                    existing = best_score.get(nb)
                    if (
                        existing is None
                        or cand_score > existing
                        or (cand_score == existing and nb_lts < last_turn_step.get(nb, 0))
                    ):
                        best_score[nb] = cand_score
                        parent[nb] = current
                        last_turn_step[nb] = nb_lts

        if goal not in parent:
            return []
        return self._reconstruct(parent, goal)

    def _bfs(self, grid: Grid3D, source: Vc) -> Dict[Vc, int]:
        distances: Dict[Vc, int] = {source: 0}
        queue: Deque[Vc] = deque([source])
        while queue:
            current = queue.popleft()
            d = distances[current]
            for nb in self._neighbours(current):
                if not grid.is_free(nb) or nb in distances:
                    continue
                distances[nb] = d + 1
                queue.append(nb)
        return distances

    def _clearance_field(self, grid: Grid3D) -> Dict[Vc, int]:
        distances: Dict[Vc, int] = {}
        queue: Deque[Vc] = deque()
        for x in range(grid.nx):
            for y in range(grid.ny):
                for z in range(grid.nz):
                    vc = (x, y, z)
                    if vc in grid.occupied:
                        distances[vc] = 0
                        queue.append(vc)
        if not queue:
            # No obstacles: uniform clearance of 0
            for x in range(grid.nx):
                for y in range(grid.ny):
                    for z in range(grid.nz):
                        distances[(x, y, z)] = 0
            return distances
        while queue:
            current = queue.popleft()
            d = distances[current]
            for nb in self._neighbours(current):
                if not grid.in_bounds(nb) or nb in distances:
                    continue
                distances[nb] = d + 1
                queue.append(nb)
        return distances

    @staticmethod
    def _reconstruct(came_from: Dict[Vc, Optional[Vc]], current: Vc) -> List[Vc]:
        path: List[Vc] = [current]
        while came_from[current] is not None:
            current = came_from[current]  # type: ignore[assignment]
            path.append(current)
        path.reverse()
        return path
