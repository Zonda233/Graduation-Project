# 01 — Coordinate System

## 1.1 Two Coordinate Spaces

The system uses two coordinate spaces throughout:

| Space | Symbol | Type | Unit | Description |
|-------|--------|------|------|-------------|
| Voxel coordinate | `vc` | `(int, int, int)` | voxel index | Integer grid index of a voxel cell |
| World coordinate | `wc` | `(float, float, float)` | metres | Blender world-space position |

The voxel grid is right-handed, Z-up (matches Blender default).

A voxel `(i, j, k)` occupies the axis-aligned box:

```
[origin_x + i*vs,  origin_x + (i+1)*vs]  ×
[origin_y + j*vs,  origin_y + (j+1)*vs]  ×
[origin_z + k*vs,  origin_z + (k+1)*vs]
```

where `vs = voxel_size` (default **0.2 m**) and `origin = (origin_x, origin_y, origin_z)` (default **(0, 0, 0)**).

---

## 1.2 Voxel Centre → World (`vc_to_wc`)

Source: [`VoxelGeometryMaps.vc_to_wc()`](../../router-layer/grid/voxel_geometry.py:55) (router layer),
[`vc_to_wc_center()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:82) (generation layer).

```
wc[i] = origin[i] + (vc[i] + 0.5) × voxel_size
```

The `+ 0.5` offset places the result at the **geometric centre** of the voxel cell.

**Example** (default config: `origin=(0,0,0)`, `voxel_size=0.2`):

```
vc = (2, 3, 1)
wc = (0 + 2.5×0.2,  0 + 3.5×0.2,  0 + 1.5×0.2)
   = (0.5,  0.7,  0.3)
```

---

## 1.3 Voxel Corner → World (`vc_to_wc_corner`)

Source: [`vc_to_wc_corner()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:132).

```
wc[i] = origin[i] + vc[i] × voxel_size
```

No half-voxel offset — returns the minimum-coordinate vertex of the voxel cell.

---

## 1.4 Arbitrary Voxel-Space Point → World (`vc_to_wc_point`)

Source: [`vc_to_wc_point()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:111).

```
wc[i] = origin[i] + float(vc[i]) × voxel_size
```

Used for fractional voxel coordinates (e.g. bounding-box centres already computed in voxel units).

---

## 1.5 World → Voxel (`wc_to_vc`)

Source: [`wc_to_vc()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:146),
[`SequentialMultiLineRouter._wc_to_vc()`](../../router-layer/routing/sequential_router.py:145).

```
vc[i] = floor((wc[i] - origin[i]) / voxel_size)
```

Returns the voxel index whose **centre** is closest to the given world point (floor snapping).

---

## 1.6 Axis Direction Strings

Six axis strings are used throughout both layers:

| String | Vector |
|--------|--------|
| `"+X"` | (1, 0, 0) |
| `"-X"` | (-1, 0, 0) |
| `"+Y"` | (0, 1, 0) |
| `"-Y"` | (0, -1, 0) |
| `"+Z"` | (0, 0, 1) |
| `"-Z"` | (0, 0, -1) |

Source: [`VoxelGeometryMaps.VEC_BY_AXIS`](../../router-layer/grid/voxel_geometry.py:20),
[`_AXIS_VECTOR`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:43).

The router layer also maps integer delta-vectors to axis strings:

```
AXIS_BY_DELTA = {
    (1,0,0): "+X",  (-1,0,0): "-X",
    (0,1,0): "+Y",  (0,-1,0): "-Y",
    (0,0,1): "+Z",  (0,0,-1): "-Z",
}
```

Source: [`VoxelGeometryMaps.AXIS_BY_DELTA`](../../router-layer/grid/voxel_geometry.py:12).

---

## 1.7 Shift Along Axis (`shift_wc`)

Source: [`VoxelGeometryMaps.shift_wc()`](../../router-layer/grid/voxel_geometry.py:70).

```
shift_wc(wc, axis, d) = wc + vec(axis) × d
```

where `vec(axis)` is the unit vector from the table above and `d` is a signed distance in metres.

---

## 1.8 Pipe Length (`pipe_length_m`)

Source: [`VoxelGeometryMaps.pipe_length_m()`](../../router-layer/grid/voxel_geometry.py:79).

```
pipe_length_m(wc_start, wc_end) = ||wc_end - wc_start||₂
```

Euclidean distance in metres.

---

## 1.9 Nominal Diameter → Outer Diameter (OD) Table

Source: [`VoxelGeometryMaps.OD_BY_NOMINAL_M`](../../router-layer/grid/voxel_geometry.py:29),
[`DN_TABLE`](../../chemical-piping-lib/chemical_piping_lib/config.py:94) (ASME B36.10M).

| Nominal (m) | Nominal (mm) | OD (m) |
|-------------|--------------|--------|
| 0.015 | DN15 | 0.02134 |
| 0.020 | DN20 | 0.02667 |
| 0.025 | DN25 | 0.03340 |
| 0.032 | DN32 | 0.04216 |
| 0.040 | DN40 | 0.04826 |
| 0.050 | DN50 | 0.06033 |
| 0.065 | DN65 | 0.07315 |
| 0.080 | DN80 | 0.08890 |
| 0.100 | DN100 | 0.11430 |
| 0.125 | DN125 | 0.14130 |
| 0.150 | DN150 | 0.16830 |
| 0.200 | DN200 | 0.21910 |

If the nominal diameter is not in the table, the generation layer falls back to `OD = nominal_diameter × 1.1` (10% oversizing heuristic).

---

## 1.10 RouterConfig Parameters

Source: [`RouterConfig`](../../router-layer/config.py:8).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `voxel_size` | 0.2 m | Edge length of one voxel cell |
| `grid_dimensions` | (20, 20, 20) | Grid size in voxels (nx, ny, nz) |
| `origin_wc` | (0, 0, 0) | World-space position of voxel (0,0,0) corner |
| `elbow_overlap_m` | 0.003 m | Extra overlap of elbow mesh into adjacent pipe |
| `tee_run_half_length_factor` | 1.5 | Run port offset = factor × OD |
| `tee_branch_half_length_factor` | 1.25 | Branch port offset = factor × OD |
| `safety_margin_voxels` | 0 | Dilation margin around routed paths |
