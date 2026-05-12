# 05 — Tee Assembly

Sources:
- [`SegmentsAndTeesAssembler`](../../router-layer/emission/segments_assembler.py:37)
- [`PipeAndTeeGeometryTrimmer`](../../router-layer/emission/geometry_trimmer.py:18)

---

## 5.1 What Is a Tee?

A **tee joint** is a three-way pipe junction. It appears when a node is shared
by more than one `LineSpec` (a "via" node). The tee is placed at the voxel
centre of the shared node and has three ports:

- **run_a** — one end of the straight-through run
- **run_b** — the other end of the straight-through run
- **branch** — the perpendicular branch

The tee is emitted as a top-level `tee_joints` entry in the output JSON, not
as a component inside any segment.

---

## 5.2 Tee Centre World Coordinate

Source: [`SegmentsAndTeesAssembler._build_tee_joints()`](../../router-layer/emission/segments_assembler.py:314)

```
wc_center = vc_to_wc(placed_node.vc, config)
          = (origin_x + (vc_x + 0.5) × vs,
             origin_y + (vc_y + 0.5) × vs,
             origin_z + (vc_z + 0.5) × vs)
```

---

## 5.3 Tee Axis Computation

Source: [`SegmentsAndTeesAssembler._build_tee_axes()`](../../router-layer/emission/segments_assembler.py:200)

For each segment that passes through the tee node, the axis is determined from
the delta between the tee voxel and its neighbour in the path:

```
delta = neighbour_vc - tee_vc          # e.g. (1, 0, 0)
axis  = AXIS_BY_DELTA[delta]           # e.g. "+X"
```

Three axes are computed:
- **run_a**: direction from tee toward the previous voxel in the first segment
- **run_b**: direction from tee toward the next voxel in the first segment
  (or the second segment's direction)
- **branch**: direction from tee toward the path of the branching segment

Specifically, for a path `[…, prev, tee, next, …]`:
```
run_a_axis = AXIS_BY_DELTA[prev_vc - tee_vc]
run_b_axis = AXIS_BY_DELTA[next_vc - tee_vc]
```

For the branch segment whose path starts at `tee_vc`:
```
branch_axis = AXIS_BY_DELTA[path[1] - tee_vc]
```

---

## 5.4 Tee Axis Normalisation Rules

Source: [`SegmentsAndTeesAssembler._normalize_tee_axes()`](../../router-layer/emission/segments_assembler.py:244)

After the raw axes are computed, three normalisation rules are applied:

**Rule 1 — run_a must be set.**
If `run_a` was not computed (the tee is at the very start of a segment with no
predecessor), it defaults to the opposite of `run_b`:
```
if run_a is None and run_b is not None:
    run_a = opposite(run_b)
```

**Rule 2 — run_b must be set, but only if not already computed.**
If `run_b` was not computed (the tee is at the very end of a segment with no
successor), it defaults to the opposite of `run_a`:
```
if run_b is None and run_a is not None:
    run_b = opposite(run_a)
```

This rule is applied **only when `run_b` was not already set by the axis
computation step**. Overwriting a computed `run_b` would corrupt L-shaped
junctions (Bug 1 fix).

**Rule 3 — branch must not collide with run axes.**
If the branch axis equals `run_a` or `run_b` (or their opposites), the branch
is reassigned to the first available perpendicular axis:
```
if branch in {run_a, run_b, opposite(run_a), opposite(run_b)}:
    branch = first axis in ["+X","-X","+Y","-Y","+Z","-Z"]
             that is not run_a, run_b, opposite(run_a), opposite(run_b)
```

---

## 5.5 Tee Port Offset Formulas

Source: [`PipeAndTeeGeometryTrimmer.tee_offset_m()`](../../router-layer/emission/geometry_trimmer.py:64)

Each tee port has a world-space position offset from the tee centre along the
port's axis. The offset is capped at `voxel_size / 2` to keep the port within
the tee's voxel cell.

**Run port offset** (run_a and run_b):
```
offset_run = min(tee_run_half_length_factor × OD,  voxel_size / 2)
           = min(1.5 × OD,  0.1)
```

**Branch port offset**:
```
offset_branch = min(tee_branch_half_length_factor × OD,  voxel_size / 2)
              = min(1.25 × OD,  0.1)
```

For DN100 (`OD = 0.11430 m`):
```
offset_run    = min(1.5 × 0.11430,  0.1) = min(0.17145, 0.1) = 0.1 m  (capped)
offset_branch = min(1.25 × 0.11430, 0.1) = min(0.14288, 0.1) = 0.1 m  (capped)
```

For DN50 (`OD = 0.06033 m`):
```
offset_run    = min(1.5 × 0.06033,  0.1) = min(0.09050, 0.1) = 0.09050 m
offset_branch = min(1.25 × 0.06033, 0.1) = min(0.07541, 0.1) = 0.07541 m
```

---

## 5.6 Tee Port World Coordinate

Source: [`PipeAndTeeGeometryTrimmer.tee_port_wc()`](../../router-layer/emission/geometry_trimmer.py:79)

```
port_wc = shift_wc(tee_wc_center, port_axis, offset)
        = tee_wc_center + offset × vec(port_axis)
```

This is the world position where a pipe end must meet the tee.

---

## 5.7 Pipe Endpoint Trimming to Tee Port

Source: [`PipeAndTeeGeometryTrimmer.tee_port_wc_for_pipe()`](../../router-layer/emission/geometry_trimmer.py:102),
[`PipeAndTeeGeometryTrimmer.trim_segment_pipes_to_tee_ports()`](../../router-layer/emission/geometry_trimmer.py:159)

The first and last pipe of each segment must have their endpoints adjusted to
meet the tee port exactly. Two details are critical:

1. The offset is applied along the **pipe's own travel axis**, not the tee port
   axis stored in the JSON.
2. The **sign** of the offset depends on whether the pipe is *departing from*
   or *arriving at* the tee.

### Sign convention

```
pipe_axis = pipe["axis"]               # e.g. "+X" (the pipe's travel direction)
offset    = tee_offset_m(tee, port_id) # run or branch half-length offset
```

**Departing pipe** — the segment's `from_port` is this tee.
The pipe leaves the tee in its travel direction, so the port face is *ahead*:
```
effective_axis = pipe_axis             # same direction as travel
pipe.wc_start  = tee_wc_center + offset × vec(effective_axis)
```

**Arriving pipe** — the segment's `to_port` is this tee.
The pipe reaches the tee from the opposite side, so the port face is *behind*
the tee centre relative to the pipe's travel direction:
```
effective_axis = opposite(pipe_axis)   # reverse of travel direction
pipe.wc_end    = tee_wc_center + offset × vec(effective_axis)
               = tee_wc_center − offset × vec(pipe_axis)
```

After adjustment, `pipe.length_m` is recomputed as `||wc_end − wc_start||₂`.

### Numeric example (Bug 5 case)

Tee `tee_01` centre: X = 2.1 m, DN100 run offset = 0.1 m.

| Segment | Role | pipe_axis | effective_axis | endpoint X |
|---------|------|-----------|----------------|------------|
| `seg_L_main_process_2_c00` | departing (`from_port`) | `+X` | `+X` | 2.1 + 0.1 = **2.2** |
| `seg_L_main_process_1_c02` | arriving (`to_port`) | `+X` | `−X` | 2.1 − 0.1 = **2.0** |

Before the fix, both cases used `+X`, giving 2.2 for the arriving pipe and
causing it to penetrate 0.2 m into the tee centre.

### Why use the pipe axis instead of the tee port axis?

The tee port axis points from the tee centre toward the pipe stub end. For a
well-formed tee the port axis and the effective pipe axis agree. But when the
router places a branch segment that immediately turns, or when the tee axis
assignment is imprecise, they can differ. Using the pipe's own axis guarantees
the endpoint lands on the pipe's centre-line at the correct distance from the
tee centre, regardless of the tee port axis stored in the JSON.

---

## 5.8 Segment Splitting at Tee Nodes

Source: [`SegmentsAndTeesAssembler._split_path_by_via()`](../../router-layer/emission/segments_assembler.py:371)

When a `LineSpec` passes through one or more via nodes (tee junctions), its
voxel path is split at each via voxel into sub-paths (slices). Each slice
becomes an independent segment in the output JSON.

```
slices = split_path_by_via(full_path, via_vcs)
```

Each slice `[vc_a, …, vc_b]` is converted to components independently, then
its first/last pipe endpoints are trimmed to the tee port positions.

---

## 5.9 Tee JSON Structure

The assembled tee joint in the output JSON:

```json
{
  "tee_id":    "tee_01",
  "vc_center": [5, 3, 1],
  "wc_center": [1.1, 0.7, 0.3],
  "ports": [
    {"port_id": "tee_01_run_a",  "axis": "-X", "connects_to_comp": "seg01_c03"},
    {"port_id": "tee_01_run_b",  "axis": "+X", "connects_to_comp": "seg02_c01"},
    {"port_id": "tee_01_branch", "axis": "+Y", "connects_to_comp": "seg03_c01"}
  ],
  "spec": {
    "main_diameter":   0.1,
    "branch_diameter": 0.1,
    "material_id":     "carbon_steel"
  }
}
```

Port IDs follow the naming convention:
```
port_id = tee_id + "_run_a"    (or "_run_b", "_branch")
```

Source: [`constants.py`](../../router-layer/constants.py:17) — `TEE_PORT_SUFFIX_RUN_A = "_run_a"`, etc.
