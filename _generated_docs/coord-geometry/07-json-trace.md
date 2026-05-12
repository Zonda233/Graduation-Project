# 07 — End-to-End JSON Trace

This document traces a single pipe run through the complete pipeline, showing
exactly how each number is computed at every stage.

**Scenario**: DN80 pipe from node `pump_out` at voxel `(2, 1, 1)` to node
`valve_in` at voxel `(2, 5, 1)`, with a 90° turn at voxel `(2, 3, 1)` going
via `(4, 3, 1)`.

Config: `voxel_size = 0.2 m`, `origin_wc = (0, 0, 0)`, `nominal_diameter = 0.08` m (DN80).

---

## Stage 0 — Router Input JSON

Source: [`VLM-layer/output/router_input_from_vlm.json`](../../VLM-layer/output/router_input_from_vlm.json)

```json
{
  "meta": {
    "voxel_grid": {
      "voxel_size_m": 0.2,
      "origin_wc": [0.0, 0.0, 0.0],
      "dimensions": [20, 20, 5]
    }
  },
  "nodes": [
    { "node_id": "pump_out",  "node_type": "EquipmentPort" },
    { "node_id": "valve_in",  "node_type": "EquipmentPort" }
  ],
  "lines": [
    {
      "line_id": "L1",
      "from_node": "pump_out",
      "to_node":   "valve_in",
      "spec": { "nominal_diameter": 0.08, "material_id": "carbon_steel" }
    }
  ]
}
```

---

## Stage 1 — Node Placement

Source: [`SimpleNodePlacer`](../../router-layer/placement/simple_node_placer.py:15)

**pump_out** placed at voxel `(2, 1, 1)`:
```
wc = (0 + (2+0.5)×0.2,  0 + (1+0.5)×0.2,  0 + (1+0.5)×0.2)
   = (0.5,  0.3,  0.3)
```

**valve_in** placed at voxel `(2, 5, 1)`:
```
wc = (0 + 2.5×0.2,  0 + 5.5×0.2,  0 + 1.5×0.2)
   = (0.5,  1.1,  0.3)
```

---

## Stage 2 — Pathfinding

Source: [`ClearanceAwareShortestPathFinder`](../../router-layer/pathfinding/clearance_path_finder.py:63)

**Elbow-spacing constraint** for DN80:
```
OD = 0.08890 m
R  = 1.5 × 0.08890 = 0.13335 m
min_straight = ceil(2 × 0.13335 / 0.2) = ceil(1.3335) = 2 voxels
```

**Voxel path found** (BFS shortest + clearance DP):
```
[(2,1,1), (2,2,1), (2,3,1), (3,3,1), (4,3,1), (4,4,1), (4,5,1)]
```

Direction sequence:
- `(2,1,1)→(2,2,1)→(2,3,1)`: axis `+Y`
- `(2,3,1)→(3,3,1)→(4,3,1)`: axis `+X`  ← turn at `(2,3,1)`, step 2
- `(4,3,1)→(4,4,1)→(4,5,1)`: axis `+Y`  ← turn at `(4,3,1)`, step 4

Turn at step 4: `(4+1) - (2+1) = 2 >= min_straight=2` ✓ (constraint satisfied)

---

## Stage 3 — Path to Components (raw)

Source: [`GenerationPathComponentConverter`](../../router-layer/emission/path_converter.py:12)

**Straight run 1**: voxels `(2,1,1)` to `(2,3,1)`, axis `+Y`, 2 hops
```
wc_start = vc_to_wc((2,1,1)) = (0.5, 0.3, 0.3)
wc_end   = vc_to_wc((2,3,1)) = (0.5, 0.7, 0.3)
length_m = 0.2 × 2 = 0.4 m
```

**Elbow at corner** `(2,3,1)`, `axis_in="+Y"`, `axis_out="+X"`:
```
wc_center = vc_to_wc((2,3,1)) = (0.5, 0.7, 0.3)
```

**Straight run 2**: voxels `(2,3,1)` to `(4,3,1)`, axis `+X`, 2 hops
```
wc_start = vc_to_wc((2,3,1)) = (0.5, 0.7, 0.3)
wc_end   = vc_to_wc((4,3,1)) = (0.9, 0.7, 0.3)
length_m = 0.2 × 2 = 0.4 m
```

**Elbow at corner** `(4,3,1)`, `axis_in="+X"`, `axis_out="+Y"`:
```
wc_center = vc_to_wc((4,3,1)) = (0.9, 0.7, 0.3)
```

**Straight run 3**: voxels `(4,3,1)` to `(4,5,1)`, axis `+Y`, 2 hops
```
wc_start = vc_to_wc((4,3,1)) = (0.9, 0.7, 0.3)
wc_end   = vc_to_wc((4,5,1)) = (0.9, 1.1, 0.3)
length_m = 0.2 × 2 = 0.4 m
```

---

## Stage 4 — Elbow Pipe Trimming

Source: [`PipeAndTeeGeometryTrimmer.trim_pipes_around_elbows()`](../../router-layer/emission/geometry_trimmer.py:26)

```
R    = 1.5 × 0.08890 = 0.13335 m
trim = R + 0.003     = 0.13635 m
```

**Elbow 1** at `(0.5, 0.7, 0.3)`, `axis_in="+Y"`, `axis_out="+X"`:
```
pipe1.wc_end   = (0.5, 0.7, 0.3) - 0.13635 × (0,1,0) = (0.5, 0.56365, 0.3)
pipe2.wc_start = (0.5, 0.7, 0.3) + 0.13635 × (1,0,0) = (0.63635, 0.7, 0.3)
```

**Elbow 2** at `(0.9, 0.7, 0.3)`, `axis_in="+X"`, `axis_out="+Y"`:
```
pipe2.wc_end   = (0.9, 0.7, 0.3) - 0.13635 × (1,0,0) = (0.76365, 0.7, 0.3)
pipe3.wc_start = (0.9, 0.7, 0.3) + 0.13635 × (0,1,0) = (0.9, 0.83635, 0.3)
```

**Recomputed lengths**:
```
pipe1.length_m = ||(0.5, 0.56365, 0.3) - (0.5, 0.3, 0.3)||
               = |0.56365 - 0.3| = 0.26365 m

pipe2.length_m = ||(0.76365, 0.7, 0.3) - (0.63635, 0.7, 0.3)||
               = |0.76365 - 0.63635| = 0.1273 m

pipe3.length_m = ||(0.9, 1.1, 0.3) - (0.9, 0.83635, 0.3)||
               = |1.1 - 0.83635| = 0.26365 m
```

---

## Stage 5 — Router Output JSON (segments)

Source: [`router-layer/output/router_output_from_vlm.json`](../../router-layer/output/router_output_from_vlm.json)

```json
{
  "segments": [
    {
      "segment_id": "L1",
      "spec": {
        "nominal_diameter": 0.08,
        "material_id": "carbon_steel"
      },
      "components": [
        {
          "comp_id":  "L1_c01",
          "type":     "Pipe",
          "vc_start": [2, 1, 1],
          "vc_end":   [2, 3, 1],
          "wc_start": [0.5, 0.3, 0.3],
          "wc_end":   [0.5, 0.56365, 0.3],
          "axis":     "+Y",
          "length_m": 0.26365
        },
        {
          "comp_id":      "L1_c02",
          "type":         "Elbow",
          "vc_center":    [2, 3, 1],
          "wc_center":    [0.5, 0.7, 0.3],
          "axis_in":      "+Y",
          "axis_out":     "+X",
          "angle_deg":    90
        },
        {
          "comp_id":  "L1_c03",
          "type":     "Pipe",
          "vc_start": [2, 3, 1],
          "vc_end":   [4, 3, 1],
          "wc_start": [0.63635, 0.7, 0.3],
          "wc_end":   [0.76365, 0.7, 0.3],
          "axis":     "+X",
          "length_m": 0.1273
        },
        {
          "comp_id":      "L1_c04",
          "type":         "Elbow",
          "vc_center":    [4, 3, 1],
          "wc_center":    [0.9, 0.7, 0.3],
          "axis_in":      "+X",
          "axis_out":     "+Y",
          "angle_deg":    90
        },
        {
          "comp_id":  "L1_c05",
          "type":     "Pipe",
          "vc_start": [4, 3, 1],
          "vc_end":   [4, 5, 1],
          "wc_start": [0.9, 0.83635, 0.3],
          "wc_end":   [0.9, 1.1, 0.3],
          "axis":     "+Y",
          "length_m": 0.26365
        }
      ]
    }
  ]
}
```

---

## Stage 6 — Generation Layer (Blender)

Source: [`chemical-piping-lib/chemical_piping_lib/scene/assembler.py`](../../chemical-piping-lib/chemical_piping_lib/scene/assembler.py)

### Pipe L1_c01

```
outer_radius = 0.08890 / 2 = 0.04445 m
depth        = 0.26365 m
axis         = "+Y"

rotation: q = (+Z).rotation_difference((0,1,0))
            = 90° around +X

location = midpoint((0.5,0.3,0.3), (0.5,0.56365,0.3))
         = (0.5, 0.43183, 0.3)
```

### Elbow L1_c02

```
corner_wc = (0.5, 0.7, 0.3)
d_in  = (0, 1, 0)   # +Y
d_out = (1, 0, 0)   # +X
R     = 0.13335 m

P_in  = (0.5, 0.7, 0.3) - 0.13335×(0,1,0) = (0.5, 0.56665, 0.3)
P_out = (0.5, 0.7, 0.3) + 0.13335×(1,0,0) = (0.63335, 0.7, 0.3)
O     = (0.5, 0.7, 0.3) - 0.13335×(0,1,0) + 0.13335×(1,0,0)
      = (0.63335, 0.56665, 0.3)

r_start = (P_in - O).normalized()
        = ((0.5-0.63335, 0.56665-0.56665, 0)/0.13335)
        = (-1, 0, 0)

r_end   = (P_out - O).normalized()
        = ((0.63335-0.63335, 0.7-0.56665, 0)/0.13335)
        = (0, 1, 0)

θ = acos((-1,0,0)·(0,1,0)) = acos(0) = π/2 = 90°

rot_axis = (-1,0,0) × (0,1,0) = (0,0,-1)  → normalised: (0,0,-1)

Arc sweeps 90° from P_in to P_out around O in the XY plane.
Object origin placed at corner_wc = (0.5, 0.7, 0.3).
```

### Pipe L1_c03

```
depth    = 0.1273 m
axis     = "+X"
location = midpoint((0.63635,0.7,0.3), (0.76365,0.7,0.3))
         = (0.7, 0.7, 0.3)
```

### Elbow L1_c04

```
corner_wc = (0.9, 0.7, 0.3)
d_in  = (1, 0, 0)   # +X
d_out = (0, 1, 0)   # +Y
R     = 0.13335 m

P_in  = (0.9, 0.7, 0.3) - 0.13335×(1,0,0) = (0.76665, 0.7, 0.3)
P_out = (0.9, 0.7, 0.3) + 0.13335×(0,1,0) = (0.9, 0.83335, 0.3)
O     = (0.9, 0.7, 0.3) - 0.13335×(1,0,0) + 0.13335×(0,1,0)
      = (0.76665, 0.83335, 0.3)
```

### Pipe L1_c05

```
depth    = 0.26365 m
axis     = "+Y"
location = midpoint((0.9,0.83635,0.3), (0.9,1.1,0.3))
         = (0.9, 0.96818, 0.3)
```

---

## Summary: Key Numbers for This Trace

| Quantity | Value |
|----------|-------|
| `voxel_size` | 0.2 m |
| DN80 OD | 0.08890 m |
| Bend radius R | 0.13335 m |
| `min_straight` | 2 voxels |
| `trim` | 0.13635 m |
| Pipe 1 trimmed length | 0.26365 m |
| Pipe 2 (between elbows) length | 0.1273 m |
| Pipe 3 trimmed length | 0.26365 m |
| Elbow arc angle | 90° |
| Elbow object origin | at `wc_center` (corner voxel centre) |
| Pipe object origin | at midpoint of `wc_start` and `wc_end` |
