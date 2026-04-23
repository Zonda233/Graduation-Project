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

Complexity: O(V + E) time and space (V = grid voxels, E = 6-neighbour edges).
"""

from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from ..grid.grid import Grid3D
from ..models.input_models import LineSpec
from ..models.types import Vc


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
            grid = grid.with_forbidden(v for v in forbidden if v not in allowed)

        waypoints: List[Vc] = [start_vc]
        if via_vc:
            waypoints.extend(via_vc)
        waypoints.append(goal_vc)

        full_path: List[Vc] = []
        for i in range(len(waypoints) - 1):
            seg_start, seg_goal = waypoints[i], waypoints[i + 1]
            force_first = start_direction if (i == 0 and start_direction) else None
            force_last = end_direction if (i == len(waypoints) - 2 and end_direction) else None
            segment = self._segment_with_directions(grid, seg_start, seg_goal, force_first, force_last)
            if not segment:
                return []
            full_path.extend(segment[1:] if full_path else segment)
        return full_path

    def _segment_with_directions(
        self,
        grid: Grid3D,
        start: Vc,
        goal: Vc,
        force_first: Optional[str],
        force_last: Optional[str],
    ) -> List[Vc]:
        if force_first:
            delta = self.DELTA_BY_AXIS.get(force_first)
            if not delta:
                return self._solve(grid, start, goal)
            first_step = (start[0] + delta[0], start[1] + delta[1], start[2] + delta[2])
            if not grid.is_free(first_step):
                return []
            mid = self._solve(grid, first_step, goal)
            return [start] + mid if mid else []

        if force_last:
            delta = self.DELTA_BY_AXIS.get(force_last)
            if not delta:
                return self._solve(grid, start, goal)
            last_step = (goal[0] - delta[0], goal[1] - delta[1], goal[2] - delta[2])
            if not grid.is_free(last_step):
                return []
            mid = self._solve(grid, start, last_step)
            if mid and goal in mid[:-1]:
                constrained = grid.with_forbidden([goal]).with_allowed([start, last_step])
                mid = self._solve(constrained, start, last_step)
            return mid + [goal] if mid else []

        return self._solve(grid, start, goal)

    @staticmethod
    def _neighbours(vc: Vc) -> List[Vc]:
        x, y, z = vc
        return [
            (x + 1, y, z), (x - 1, y, z),
            (x, y + 1, z), (x, y - 1, z),
            (x, y, z + 1), (x, y, z - 1),
        ]

    def _solve(self, grid: Grid3D, start: Vc, goal: Vc) -> List[Vc]:
        if not grid.is_free(start) or not grid.is_free(goal):
            return []

        dist_start = self._bfs(grid, start)
        shortest_len = dist_start.get(goal)
        if shortest_len is None:
            return []

        dist_goal = self._bfs(grid, goal)
        clearance = self._clearance_field(grid)

        best_score: Dict[Vc, Tuple[int, int]] = {
            start: (clearance.get(start, 0), clearance.get(start, 0))
        }
        parent: Dict[Vc, Optional[Vc]] = {start: None}

        nodes_by_dist: Dict[int, List[Vc]] = {}
        for node, dist in dist_start.items():
            nodes_by_dist.setdefault(dist, []).append(node)

        for step in range(shortest_len):
            for current in nodes_by_dist.get(step, []):
                current_score = best_score.get(current)
                if current_score is None:
                    continue
                for nb in self._neighbours(current):
                    if not grid.is_free(nb):
                        continue
                    if dist_start.get(nb) != step + 1:
                        continue
                    if dist_goal.get(nb) != shortest_len - (step + 1):
                        continue
                    nb_clear = clearance.get(nb, 0)
                    cand = (min(current_score[0], nb_clear), current_score[1] + nb_clear)
                    if best_score.get(nb) is None or cand > best_score[nb]:
                        best_score[nb] = cand
                        parent[nb] = current

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
