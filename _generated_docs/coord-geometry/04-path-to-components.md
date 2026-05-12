# 04 — Path to Components & Geometry Trimming

Sources:
- [`GenerationPathComponentConverter`](../../router-layer/emission/path_converter.py:12)
- [`PipeAndTeeGeometryTrimmer`](../../router-layer/emission/geometry_trimmer.py:18)

---

## 4.1 Overview

After pathfinding produces a voxel path `[vc_0, vc_1, …, vc_n]`, the
`GenerationPathComponentConverter` converts it into a list of schema-oriented
component dicts — alternating **Pipe** and **Elbow** entries — that the
generation layer can directly instantiate as Blender objects.

The conversion has three phases:

1. Scan the path for straight runs and corners → build raw Pipe/Elbow dicts
2. Call `trim_pipes_around_elbows()` to shorten pipe endpoints to the elbow
   tangent points
3. (Later, in `SegmentsAndTeesAssembler`) call
   `trim_segment_pipes_to_tee_ports()` to shorten the first/last pipe of each
   segment to the tee port position

---

## 4.2 Immediate Backtrack Removal

Source: [`GenerationPathComponentConverter._remove_immediate_backtracks()`](../../router-layer/emission/path_converter.py:83)

Before conversion, any A→B→A zigzag in the voxel path is removed. If three
consecutive voxels satisfy `path[i+2] == path[i]`, the middle voxel is
deleted. This is repeated until no more backtracks exist.

---

## 4.3 Straight Run Detection

The converter scans the path for **direction changes** (corners). A straight
run is a maximal sub-sequence of voxels all moving in the same axis direction.

For a straight run from index `i` to index `j` (inclusive):

```
axis = AXIS_BY_DELTA[vc_{i+1} - vc_i]   # e.g. "+Y"

wc_start = vc_to_wc(vc_i,   config)
wc_end   = vc_to_wc(vc_j,   config)
length_m = voxel_size × (j - i)          # integer hop count × voxel size
```

The resulting **Pipe** component dict:

```json
{
  "comp_id":   "seg01_c01",
  "type":      "Pipe",
  "vc_start":  [i_x, i_y, i_z],
  "vc_end":    [j_x, j_y, j_z],
  "wc_start":  [wx_start, wy_start, wz_start],
  "wc_end":    [wx_end,   wy_end,   wz_end],
  "axis":      "+Y",
  "length_m":  0.6
}
```

Source: [`GenerationPathComponentConverter._build_pipe_component()`](../../router-layer/emission/path_converter.py:94)

---

## 4.4 Elbow Detection

A corner occurs at voxel `vc_k` where the direction changes from `axis_in` to
`axis_out`. The **Elbow** component dict:

```json
{
  "comp_id":      "seg01_c02",
  "type":         "Elbow",
  "vc_center":    [k_x, k_y, k_z],
  "wc_center":    [wx_k, wy_k, wz_k],
  "axis_in":      "+Y",
  "axis_out":     "+X",
  "angle_deg":    90
}
```

where:
```
wc_center = vc_to_wc(vc_k, config)
```

Source: [`GenerationPathComponentConverter._build_elbow_component()`](../../router-layer/emission/path_converter.py:114)

---

## 4.5 Elbow Pipe Trimming

Source: [`PipeAndTeeGeometryTrimmer.trim_pipes_around_elbows()`](../../router-layer/emission/geometry_trimmer.py:26)

After the raw components are built, the pipe endpoints adjacent to each elbow
are shortened so they end exactly at the elbow's tangent points (where the
straight pipe meets the bend arc).

**Bend radius:**
```
R = 1.5 × OD(nominal_diameter)
```

**Trim distance** (includes a small overlap so the elbow mesh seals against
the pipe end):
```
trim = R + elbow_overlap_m        (elbow_overlap_m = 0.003 m by default)
```

**Endpoint adjustment:**

For the pipe arriving at the elbow corner from direction `axis_in`:
```
prev_pipe.wc_end = shift_wc(corner_wc, axis_in, -trim)
                 = corner_wc - trim × vec(axis_in)
```

For the pipe departing from the elbow corner in direction `axis_out`:
```
next_pipe.wc_start = shift_wc(corner_wc, axis_out, +trim)
                   = corner_wc + trim × vec(axis_out)
```

After adjusting endpoints, the pipe length is recomputed:
```
pipe.length_m = ||wc_end - wc_start||₂
```

**Special case — first pipe of segment (no preceding elbow):**
`wc_start` is left at the voxel centre of the start node. It will be adjusted
later by `trim_segment_pipes_to_tee_ports()` if the segment connects to a tee.

**Special case — last pipe of segment (no following elbow):**
`wc_end` is left at the voxel centre of the end node. Same treatment.

---

## 4.6 Pipe Length After Trimming

For a pipe between two elbows, the trimmed length is:

```
raw_length = voxel_size × (hop_count)
trimmed_length = raw_length - 2 × trim
               = raw_length - 2 × (R + elbow_overlap_m)
```

For DN80 at `voxel_size = 0.2 m`, `R = 0.13335 m`, `elbow_overlap_m = 0.003 m`:
```
trim = 0.13335 + 0.003 = 0.13635 m
```

A 3-voxel straight run (0.6 m) between two elbows becomes:
```
trimmed_length = 0.6 - 2 × 0.13635 = 0.3273 m
```

---

## 4.7 Component Ordering

The final component list for a segment alternates Pipe and Elbow:

```
[Pipe_0, Elbow_0, Pipe_1, Elbow_1, …, Pipe_n]
```

- Always starts and ends with a Pipe.
- Each Elbow is sandwiched between two Pipes.
- If the path has no corners, the segment has exactly one Pipe and no Elbows.
