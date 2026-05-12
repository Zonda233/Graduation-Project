# 03 — Pathfinding

Source: [`ClearanceAwareShortestPathFinder`](../../router-layer/pathfinding/clearance_path_finder.py:63),
[`SequentialMultiLineRouter`](../../router-layer/routing/sequential_router.py:15)

---

## 3.1 Overview

The router finds a voxel path for each `LineSpec` (a pipe run connecting two
nodes). The algorithm is a **two-phase approach**:

1. **Phase 1 — BFS shortest-path manifold.** Find the minimum hop-count
   distance from the goal to every reachable voxel. This defines the set of
   all shortest paths.

2. **Phase 2 — Clearance-maximising DP.** Walk from start to goal, always
   staying on the shortest-path manifold, but among equal-length options
   preferring voxels with higher clearance (distance to nearest obstacle).
   Also enforces the elbow-spacing constraint.

The result is a list of voxel coordinates `[vc_0, vc_1, …, vc_n]` where
consecutive voxels are 6-connected neighbours (differ by exactly 1 in one
axis).

---

## 3.2 Grid and Occupancy

Source: [`Grid3D`](../../router-layer/grid/grid.py:10)

The grid is a 3-D boolean occupancy map of size `nx × ny × nz`. A voxel is
**free** if it is not in the `occupied` set.

Fields:
- `nx, ny, nz` — grid dimensions
- `occupied: Set[Vc]` — set of blocked voxels
- `voxel_size: float` — edge length in metres (default 0.2 m)

After each line is routed, its voxels (plus a dilation margin of
`safety_margin_voxels`) are added to the occupied set, blocking them for
subsequent lines.

---

## 3.3 Phase 1 — BFS Shortest-Path Manifold

Source: [`ClearanceAwareShortestPathFinder._bfs()`](../../router-layer/pathfinding/clearance_path_finder.py:282)

Standard breadth-first search from the **goal** voxel over the 6-connected
free voxels. Produces a distance map `dist[v]` = minimum number of steps from
`v` to the goal.

The 6 neighbours of voxel `(x, y, z)` are:
```
(x±1, y, z),  (x, y±1, z),  (x, y, z±1)
```

Only free voxels are enqueued. If the goal is unreachable, `find_path` returns
`None`.

---

## 3.4 Phase 2 — Clearance Field

Source: [`ClearanceAwareShortestPathFinder._clearance_field()`](../../router-layer/pathfinding/clearance_path_finder.py:295)

A second BFS from **all occupied voxels simultaneously** (multi-source BFS)
computes `clearance[v]` = the Chebyshev distance from voxel `v` to the nearest
occupied voxel. Higher clearance means more open space around the pipe.

---

## 3.5 Phase 2 — Clearance-Maximising DP with Elbow-Spacing Constraint

Source: [`ClearanceAwareShortestPathFinder._solve()`](../../router-layer/pathfinding/clearance_path_finder.py:184)

The DP walks from `start` toward `goal`, always choosing the neighbour `nb`
that satisfies:

1. `dist[nb] == dist[current] - 1` (stays on the shortest-path manifold)
2. `nb` is free
3. The elbow-spacing constraint is satisfied (see §3.6)

Among all valid neighbours, the one with the **highest clearance** is chosen.
Ties are broken by a secondary sort on the voxel coordinate tuple (for
determinism).

The DP state per voxel `v` is:
- `came_from[v]` — predecessor voxel (for path reconstruction)
- `last_turn_step[v]` — the step index at which the most recent direction
  change occurred on the path leading to `v`

---

## 3.6 Elbow-Spacing Constraint

Source: [`ClearanceAwareShortestPathFinder._min_straight_voxels()`](../../router-layer/pathfinding/clearance_path_finder.py:115)

Two consecutive elbows must be separated by at least `min_straight` voxels of
straight pipe, otherwise their bend arcs physically overlap.

**Formula:**

```
R = 1.5 × OD(nominal_diameter)          # bend radius (ASME B16.9 long-radius)
min_straight = ceil(2R / voxel_size)
```

For DN80 (`OD = 0.08890 m`) at `voxel_size = 0.2 m`:
```
R = 1.5 × 0.08890 = 0.13335 m
min_straight = ceil(2 × 0.13335 / 0.2) = ceil(1.3335) = 2 voxels
```

**Enforcement in the DP:**

At each step `s`, when considering a direction change (turn) at voxel `nb`:

```
is_turn = (dir_in is not None) and (dir_out != dir_in)

if is_turn and min_straight > 0:
    if (s + 1) - last_turn_step[current] < min_straight:
        skip nb   # too close to previous elbow
```

If the turn is accepted, `last_turn_step[nb] = s + 1`. Otherwise it inherits
`last_turn_step[current]`.

The sentinel initial value is `last_turn_step[start] = -(min_straight + 1)`,
ensuring the first turn is never blocked.

If `line_ctx` is `None` (no diameter information), `min_straight = 0` and the
constraint is disabled.

---

## 3.7 Sequential Multi-Line Routing

Source: [`SequentialMultiLineRouter.route_all_lines()`](../../router-layer/routing/sequential_router.py:18)

Lines are routed one by one in the order they appear in the input. After each
line is routed:

1. The path voxels are added to the grid's occupied set.
2. If `safety_margin_voxels > 0`, the path is dilated by that many voxels in
   all 6 directions (Manhattan dilation) before blocking.

**Custom module blocking:**
If a node is of type `CustomModule`, its entire voxel bounding box (extent +
clearance) is blocked before routing begins, preventing pipes from passing
through equipment bodies.

The bounding box is computed as:
```
box_min[i] = center_vc[i] - floor(extent[i] / 2) - clearance
box_max[i] = center_vc[i] + floor(extent[i] / 2) + clearance
```

where `center_vc` is derived from the node's `wc_center` property:
```
center_vc[i] = floor((wc_center[i] - origin[i]) / voxel_size)
```

---

## 3.8 Path Segment with Directions

Source: [`ClearanceAwareShortestPathFinder._segment_with_directions()`](../../router-layer/pathfinding/clearance_path_finder.py:141)

Before the DP, the start and goal voxels are extended by one step in their
required entry/exit directions (if specified by the `LineSpec`). This forces
the path to leave the start node in the correct direction and arrive at the
goal from the correct direction.

If a node has a `direction` constraint (e.g. `"+Y"`), the path must begin/end
with a step in that direction. The extended start/goal voxels are:

```
extended_start = start_vc + delta(required_start_direction)
extended_goal  = goal_vc  + delta(required_goal_direction)
```

These extension voxels are temporarily marked free if they happen to be
occupied (to allow the path to pass through the node's own footprint).
