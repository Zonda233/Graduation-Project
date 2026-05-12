# 06 — Generation Layer: Per-Component Geometry

Source: [`chemical-piping-lib/chemical_piping_lib/assets/`](../../chemical-piping-lib/chemical_piping_lib/assets/)

The generation layer reads the router output JSON and instantiates Blender
objects for each component. All geometry is built in world space using
`mathutils.Vector` arithmetic.

---

## 6.1 Pipe

Source: [`Pipe`](../../chemical-piping-lib/chemical_piping_lib/assets/pipe.py:64)

### JSON fields consumed

```json
{
  "comp_id":   "seg01_c01",
  "type":      "Pipe",
  "wc_start":  [0.5, 0.7, 0.1],
  "wc_end":    [0.5, 1.3, 0.1],
  "axis":      "+Y",
  "length_m":  0.6
}
```

### Geometry construction

1. **Cross-section** is resolved from `spec.nominal_diameter` via the DN table:
   ```
   outer_radius = OD / 2
   wall_thickness = from DN table (used only when PIPE_HOLLOW = True)
   ```

2. **Cylinder** is built along the canonical `+Z` axis with:
   ```
   depth = length_m
   radius = outer_radius
   ```
   If `PIPE_HOLLOW = True`, a tube (hollow cylinder) is built instead.

3. **Rotation**: the object is rotated so its local `+Z` aligns with `axis`:
   ```
   q = rotation_from_build_axis(axis_to_vec(axis))
   obj.rotation_quaternion = q
   ```
   Special cases in [`rotation_from_build_axis()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:181):
   - If `axis == "+Z"`: identity quaternion (no rotation)
   - If `axis == "-Z"`: 180° rotation around `+X` (avoids degenerate cross product)
   - Otherwise: `q = (+Z).rotation_difference(target)`

4. **Translation**: the object origin is placed at the pipe midpoint:
   ```
   obj.location = midpoint(wc_start, wc_end)
                = (wc_start + wc_end) × 0.5
   ```

5. **Ports** (for connection validation):
   ```
   ports = {"start": wc_start, "end": wc_end}
   ```

### Optional flanges

If `spec.with_flanges = True`, a [`Flange`](../../chemical-piping-lib/chemical_piping_lib/assets/flange.py) object is built at each end:
- Start flange: `wc_face = wc_start`, `face_axis = opposite(axis)`
- End flange: `wc_face = wc_end`, `face_axis = axis`

---

## 6.2 Elbow

Source: [`Elbow`](../../chemical-piping-lib/chemical_piping_lib/assets/elbow.py:63)

### JSON fields consumed

```json
{
  "comp_id":       "seg01_c02",
  "type":          "Elbow",
  "wc_center":     [0.5, 1.3, 0.1],
  "axis_in":       "+Y",
  "axis_out":      "+Z",
  "angle_deg":     90,
  "bend_radius_m": 0.13335
}
```

If `bend_radius_m` is absent, the default is `1.5 × OD`.

### Arc centre-line computation

Source: [`compute_elbow_arc()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:249)

Let:
```
d_in  = axis_to_vec(axis_in)    # unit vector of incoming direction
d_out = axis_to_vec(axis_out)   # unit vector of outgoing direction
R     = bend_radius
```

**Tangent points** (where straight pipe meets the arc):
```
P_in  = corner_wc - R × d_in    # end of incoming straight pipe
P_out = corner_wc + R × d_out   # start of outgoing straight pipe
```

**Bending-circle centre**:
```
O = corner_wc - R × d_in + R × d_out
```

This satisfies `|O - P_in| = R` and `|O - P_out| = R` exactly.

**Parametric arc sweep** (n_segments steps from P_in to P_out):
```
r_start = (P_in  - O).normalized()   # unit radial vector at arc start
r_end   = (P_out - O).normalized()   # unit radial vector at arc end

cos_θ = clamp(r_start · r_end, -1, 1)
θ     = acos(cos_θ)                  # total arc angle (radians)

rot_axis = (r_start × r_end).normalized()   # normal to bend plane

for i in 0 … n_segments:
    t       = i / n_segments
    angle_i = t × θ
    rot_mat = Matrix.Rotation(angle_i, 3, rot_axis)
    r_i     = rot_mat @ r_start              # radial unit vector at step i
    centre_i = O + R × r_i                  # point on arc centre-line
    tangent_i = (rot_axis × r_i).normalized()  # pipe axis direction at step i
```

The result is a list of `(centre_i, tangent_i)` pairs.

**Error conditions**:
- If `axis_in == axis_out`: raises `ValueError` (straight pipe, not an elbow)
- If `axis_in == opposite(axis_out)`: raises `ValueError` (180° bend — use two 90° elbows)

### Geometry construction

1. The arc is extended by `_OVERLAP = 0.003 m` at both ends (one extra ring
   prepended and appended) so the elbow mesh slightly overlaps the adjacent
   pipe ends, preventing visible seams.

2. For each `(centre_i, tangent_i)` pair, a ring of vertices is placed at
   `centre_i` with the ring plane perpendicular to `tangent_i`.

3. Adjacent rings are bridged with quad faces.

4. Both open ends are capped with n-gon faces.

5. All vertex positions are in world space. The object origin is set to
   `wc_center` (the geometric corner of the bend):
   ```
   for vert in bm.verts:
       vert.co -= wc_center        # make positions relative to origin
   obj.location = wc_center        # place origin at corner
   ```

6. **Ports**:
   ```
   ports = {"inlet": arc[0].centre, "outlet": arc[-1].centre}
   ```

---

## 6.3 Tee

Source: [`Tee`](../../chemical-piping-lib/chemical_piping_lib/assets/tee.py:77)

### JSON fields consumed

```json
{
  "tee_id":    "tee_01",
  "wc_center": [1.1, 0.7, 0.3],
  "ports": [
    {"port_id": "tee_01_run_a",  "axis": "-X"},
    {"port_id": "tee_01_run_b",  "axis": "+X"},
    {"port_id": "tee_01_branch", "axis": "+Y"}
  ],
  "spec": {
    "main_diameter":   0.1,
    "branch_diameter": 0.1,
    "material_id":     "carbon_steel"
  }
}
```

### Port identification

The tee identifies run vs branch automatically from the port axes:
- Two ports whose axes are **anti-parallel** (opposite strings) → the **run**
- The remaining port → the **branch**

If no anti-parallel pair exists, a `ValueError` is raised.

### Geometry construction

1. **Main run cylinder** (centred at `wc_center`, axis = `run_b_axis`):
   ```
   run_length = min(3 × main_OD,  voxel_size)
   ```
   Built along `+Z`, then rotated to `run_b_axis`, placed at `wc_center`.

2. **Branch cylinder** (centred at `wc_center`, axis = `branch_axis`):
   ```
   branch_length = min(2.5 × main_OD,  voxel_size)
   ```
   Built along `+Z`, then rotated to `branch_axis`, placed at `wc_center`.

3. **Boolean UNION**: the branch cylinder is unioned into the run cylinder
   using Blender's MANIFOLD boolean solver (with fallback). The branch object
   is deleted after the union.

4. **Port world positions** (computed after build, used for connection
   validation):
   ```
   port_run_a   = wc_center + (run_length / 2)   × vec(run_a_axis)
   port_run_b   = wc_center + (run_length / 2)   × vec(run_b_axis)
   port_branch  = wc_center + (branch_length / 2) × vec(branch_axis)
   ```

---

## 6.4 Tank

Source: [`TankBuilder`](../../router-layer/assets/tank_builder.py) (router layer emits the asset dict;
generation layer builds it via the `Tank` asset class).

Tanks are emitted as `assets` entries in the output JSON with `type = "Tank"`.
The geometry is a vertical cylinder:

```
wc_center = vc_to_wc(placed_node.vc, config)
```

The tank's voxel extent and world-space dimensions come from the node's
`properties` dict (`module_voxel_extent`, `size_xyz_m`).

Ports are placed on the cylindrical shell at the world coordinates specified
in `port_local_wc` (local offsets from the tank centre, converted to world
space by adding `wc_center`).

---

## 6.5 CustomModule

Source: [`custom_module.py`](../../chemical-piping-lib/chemical_piping_lib/assets/custom_module.py)

Custom modules are equipment items with arbitrary geometry (imported meshes or
procedural shapes). They are emitted as `assets` entries with `type =
"CustomModule"`.

The module is placed at:
```
obj.location = wc_center
```

Ports are at the world coordinates specified in the `ports` array of the asset
dict. Each port has:
```
port_wc = wc_center + local_wc_offset
```

where `local_wc_offset` comes from `port.local_wc` in the JSON.

---

## 6.6 Instrument

Source: [`instrument.py`](../../chemical-piping-lib/chemical_piping_lib/assets/instrument.py)

Instruments (flow meters, pressure gauges, etc.) are emitted as `assets`
entries with `type = "Instrument"`. They are placed at:
```
obj.location = wc_center
```

Signal lines connecting instruments to their process connections are emitted
as separate `SignalLine` components (straight lines in Blender, not physical
pipes).

---

## 6.7 Rotation Convention (All Assets)

All assets are built along the canonical `+Z` axis and then rotated to their
target direction using a quaternion computed by
[`rotation_from_build_axis()`](../../chemical-piping-lib/chemical_piping_lib/utils/coords.py:181):

```
q = rotation_from_build_axis(target_vector)
```

where `target_vector = axis_to_vec(axis_string)`.

The object's `rotation_mode` is set to `'QUATERNION'` to avoid Euler
gimbal-lock.

Special cases:
- `target == +Z`: identity quaternion `(1, 0, 0, 0)`
- `target == -Z`: 180° around `+X` → quaternion `(0, 1, 0, 0)`
- Otherwise: `q = (+Z).rotation_difference(target)`
