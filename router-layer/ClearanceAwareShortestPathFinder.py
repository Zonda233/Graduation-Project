from __future__ import annotations

"""
ClearanceAwareShortestPathFinder
================================

本文件内嵌算法文档，描述当前路由层的核心寻路策略。该策略用于在体素网格中生成
6-邻接路径，并满足以下目标顺序（按优先级）：

1) 主目标（硬约束）：路径长度最短（单位步长下的最短路径）。
2) 次目标（软偏好）：在所有最短路径中，优先选择远离已占用体素（已有管线/障碍）的路径。

设计背景
--------
- 在工艺布管场景中，很多候选路径具备相同的曼哈顿长度和转折数。
- 传统 A* 在同代价并列节点上通常由遍历顺序决定结果，容易出现“贴着已有管线走”的视觉问题。
- 工程上更希望“等长情况下尽量拉开净距”，减少不必要的挤靠与后续碰撞风险。

算法总览
--------
该实现不是“加权 A* 折中长度与净距”，而是“两阶段最优化”，以保证最短路最优性不被破坏：

阶段 A：最短路流形构建
  - 对 free voxels 做 BFS，得到 dist_start。
  - shortest_len = dist_start[goal] 即最短长度。
  - 再从 goal 做 BFS，得到 dist_goal。
  - 一个节点 n 位于某条最短路上，当且仅当：
      dist_start[n] + dist_goal[n] == shortest_len

阶段 B：最短路集合上的净距最大化
  - 先做一次多源 BFS，源点为 occupied voxels，得到 clearance(v)：
      每个体素到最近 blocked 体素的曼哈顿距离。
  - 在“最短路 DAG”上做动态规划，状态分数为二元组：
      score(path) = (path 上最小 clearance, path 上 clearance 累加和)
  - 采用词典序最大化该二元组：
      先最大化瓶颈净距（min clearance），再最大化整体离障趋势（sum clearance）。

正确性与性质
------------
- 最短性：仅在最短路 DAG 内转移，输出路径长度恒等于 shortest_len。
- 稳定性：对并列最短路给出确定性的净距偏好，不再依赖“邻居遍历偶然顺序”。
- 可解释性：输出可解释为“最短路径集合里最不挤的一条”。

复杂度（网格体素数记为 V，边数记为 E，6-邻接下 E=O(V)）
--------------------------------------------------------
- dist_start BFS：O(V + E)
- dist_goal BFS：O(V + E)
- clearance 多源 BFS：O(V + E)
- DAG 动态规划：O(E_shortest) <= O(E)
- 总体：O(V + E)，空间 O(V)

与端点方向约束的关系
------------------
- 若指定 start_direction，则强制第一步朝该方向，再对子问题做上述最短+净距策略。
- 若指定 end_direction，则强制最后一步方向（通过固定倒数第二点）后求解子问题。
- 若方向不可行（第一步/最后一步越界或被占用），直接返回空路径。

边界与退化情况
--------------
- 若 start/goal 不可通行：返回空。
- 若全图无 occupied：clearance 字段统一为 0，净距 tie-break 退化为无偏好，但仍保持最短性。
- 若 forbidden 存在，会先写入临时 grid.occupied（start/goal/via 保持可用）。
"""

from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from .IPathFinder import IPathFinder
from .RouterInputModels import LineSpec
from .domain_types import Vc
from .grid import Grid3D


class ClearanceAwareShortestPathFinder(IPathFinder):
    """6-neighbour shortest-path finder with clearance-aware tie-break among equal-length paths."""

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
                return self._shortest_segment_with_clearance_tiebreak(grid, start, goal)
            first_step = (start[0] + delta[0], start[1] + delta[1], start[2] + delta[2])
            if not grid.is_free(first_step):
                return []
            mid = self._shortest_segment_with_clearance_tiebreak(grid, first_step, goal)
            return [start] + mid if mid else []
        if force_last:
            delta = self.DELTA_BY_AXIS.get(force_last)
            if not delta:
                return self._shortest_segment_with_clearance_tiebreak(grid, start, goal)
            last_step = (goal[0] - delta[0], goal[1] - delta[1], goal[2] - delta[2])
            if not grid.is_free(last_step):
                return []
            mid = self._shortest_segment_with_clearance_tiebreak(grid, start, last_step)
            if mid and goal in mid[:-1]:
                constrained_grid = grid.with_forbidden([goal]).with_allowed([start, last_step])
                mid = self._shortest_segment_with_clearance_tiebreak(constrained_grid, start, last_step)
            return mid + [goal] if mid else []
        return self._shortest_segment_with_clearance_tiebreak(grid, start, goal)

    @staticmethod
    def _neighbours(vc: Vc) -> List[Vc]:
        x, y, z = vc
        return [(x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)]

    def _shortest_segment_with_clearance_tiebreak(self, grid: Grid3D, start: Vc, goal: Vc) -> List[Vc]:
        if not grid.is_free(start) or not grid.is_free(goal):
            return []
        dist_start = self._bfs_distance_map(grid, start)
        shortest_len = dist_start.get(goal)
        if shortest_len is None:
            return []
        dist_goal = self._bfs_distance_map(grid, goal)
        clearance = self._distance_to_blocked_field(grid)

        best_score: Dict[Vc, Tuple[int, int]] = {start: (clearance.get(start, 0), clearance.get(start, 0))}
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
                    cand_score = (min(current_score[0], nb_clear), current_score[1] + nb_clear)
                    prev_score = best_score.get(nb)
                    if prev_score is None or cand_score > prev_score:
                        best_score[nb] = cand_score
                        parent[nb] = current

        if goal not in parent:
            return []
        return self._reconstruct_path(parent, goal)

    def _bfs_distance_map(self, grid: Grid3D, source: Vc) -> Dict[Vc, int]:
        distances: Dict[Vc, int] = {source: 0}
        queue: Deque[Vc] = deque([source])
        while queue:
            current = queue.popleft()
            current_dist = distances[current]
            for nb in self._neighbours(current):
                if not grid.is_free(nb):
                    continue
                if nb in distances:
                    continue
                distances[nb] = current_dist + 1
                queue.append(nb)
        return distances

    def _distance_to_blocked_field(self, grid: Grid3D) -> Dict[Vc, int]:
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
            for x in range(grid.nx):
                for y in range(grid.ny):
                    for z in range(grid.nz):
                        distances[(x, y, z)] = 0
            return distances
        while queue:
            current = queue.popleft()
            current_dist = distances[current]
            for nb in self._neighbours(current):
                if not grid.in_bounds(nb):
                    continue
                if nb in distances:
                    continue
                distances[nb] = current_dist + 1
                queue.append(nb)
        return distances

    @staticmethod
    def _reconstruct_path(came_from: Dict[Vc, Optional[Vc]], current: Vc) -> List[Vc]:
        path: List[Vc] = [current]
        while came_from[current] is not None:
            current = came_from[current]  # type: ignore[assignment]
            path.append(current)
        path.reverse()
        return path

