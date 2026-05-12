# Coordinate & Geometry Math — Documentation Index

This folder documents all coordinate transformations and geometry calculations
from the router layer through the generation layer.

## Files

| File | Contents |
|------|----------|
| [01-coordinate-system.md](01-coordinate-system.md) | Voxel ↔ world coordinate system, axis conventions, DN/OD table |
| [02-node-placement.md](02-node-placement.md) | Node placement algorithm: topology seed map, anchor search, shell snapping |
| [03-pathfinding.md](03-pathfinding.md) | Two-phase BFS pathfinding, clearance DP, elbow-spacing constraint |
| [04-path-to-components.md](04-path-to-components.md) | Voxel path → Pipe/Elbow component conversion, geometry trimming |
| [05-tee-assembly.md](05-tee-assembly.md) | Tee axis computation, normalization rules, port offset formulas |
| [06-generation-layer.md](06-generation-layer.md) | Generation-layer per-component geometry: Pipe, Elbow, Tee, Tank, Instrument |
| [07-json-trace.md](07-json-trace.md) | End-to-end JSON trace: router input → router output → Blender scene |

## Quick Reference: Key Formulas

```
wc[i] = origin[i] + (vc[i] + 0.5) × voxel_size          # voxel centre → world
bend_radius R = 1.5 × OD                                   # HG/T 21635
min_straight = ceil(2R / voxel_size)                       # elbow spacing constraint
trim = R + elbow_overlap_m (= 0.003 m)                     # pipe endpoint trim
tee_run_offset = min(1.5 × OD, voxel_size / 2)            # run port offset
tee_branch_offset = min(1.25 × OD, voxel_size / 2)        # branch port offset
elbow arc centre O = corner_wc - R×d_in + R×d_out         # bend-circle centre
pipe object location = midpoint(wc_start, wc_end)          # Blender object origin
```
