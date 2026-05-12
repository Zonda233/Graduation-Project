# 02 — Node Placement

Source: [`SimpleNodePlacer`](../../router-layer/placement/simple_node_placer.py:15)

Node placement converts each `NodeSpec` (from the router input JSON) into a
`PlacedNode` — a concrete voxel coordinate `vc` and its corresponding world
coordinate `wc`.

---

## 2.1 Overall Algorithm

```
for each NodeSpec in router_input.nodes:
    1. Resolve seed (x_norm, y_norm) in [0,1]²
    2. Convert seed to candidate voxel (vx, vy)
    3. Resolve candidate Z layers
    4. Search Chebyshev shells for a free anchor voxel
    5. Compute wc = vc_to_wc(anchor_vc)
    6. Store PlacedNode(vc=anchor_vc, wc=wc)
```

After all nodes are placed, [`EquipmentPortShellSnapper`](../../router-layer/snapping/shell_snapper.py:15)
snaps signal ports onto the cylindrical shell of their parent tank.

---

## 2.2 Topology Seed Map

Source: [`SimpleNodePlacer._topology_seed_map()`](../../router-layer/placement/simple_node_placer.py:273)

If a node has no explicit `placement_hint`, its 2-D seed `(x_norm, y_norm)` is
derived from the graph topology of the pipeline:

**Step 1 — Build adjacency.**
For each `LineSpec` connecting node A to node B, record an undirected edge
`A ↔ B`. Also record directed edges for explicit `from_node → to_node` hints.

**Step 2 — Topological sort.**
Perform a DFS-based topological sort on the directed edges. Nodes with no
incoming edges are roots. Isolated nodes (no edges) are appended at the end.

**Step 3 — Depth assignment.**
Each node receives a depth `d` = its position in the topological order.
Nodes at the same depth are grouped into a "column".

**Step 4 — Barycenter Y ordering.**
Within each column, nodes are sorted by the average Y-seed of their already-
placed neighbours (barycenter heuristic — minimises edge crossings).

**Step 5 — Normalised (x, y) seeds.**
```
x_norm = column_index / max(num_columns - 1, 1)
y_norm = row_index_within_column / max(column_size - 1, 1)
```

Both values are in `[0, 1]`. If a node has no topology information, the
default seed `(0.5, 0.5)` is used (centre of the grid).

---

## 2.3 Seed → Candidate Voxel

Source: [`SimpleNodePlacer._to_seed_voxel()`](../../router-layer/placement/simple_node_placer.py:115)

```
vx = clamp(int(x_norm × nx), 0, nx - 1)
vy = clamp(int(y_norm × ny), 0, ny - 1)
```

where `nx`, `ny` are the grid dimensions in X and Y.

If the node has an explicit `placement_hint.wc` (world coordinate), it is
converted to a voxel seed via:

```
vc_seed[i] = floor((hint_wc[i] - origin[i]) / voxel_size)
```

---

## 2.4 Candidate Z Layers

Source: [`SimpleNodePlacer._candidate_layers()`](../../router-layer/placement/simple_node_placer.py:148)

- If the node specifies a `preferred_layer` list, those Z indices are tried first.
- Otherwise the default layer list from `RouterConfig` is used (typically `[1]`).
- Layers are clamped to `[0, nz - 1]`.

---

## 2.5 Chebyshev Shell Anchor Search

Source: [`SimpleNodePlacer._find_anchor()`](../../router-layer/placement/simple_node_placer.py:239)

For each candidate Z layer, the algorithm searches outward from the seed voxel
in Chebyshev shells of increasing radius `r = 0, 1, 2, …, max_search_radius`:

```
for r in range(0, max_search_radius + 1):
    for (dx, dy) in _candidate_xy_offsets(r):   # all (dx,dy) with max(|dx|,|dy|) == r
        anchor = (vx + dx, vy + dy, vz)
        if _is_anchor_free(anchor):
            return anchor
```

`_candidate_xy_offsets(r)` enumerates all integer offsets on the Chebyshev
shell of radius `r` (the perimeter of the square `[-r,r]²`), sorted by
Euclidean distance from the origin so closer candidates are tried first.

**Free anchor check** (`_is_anchor_free`):
The expanded bounding box of the node must lie entirely within the grid and
must not overlap any already-occupied voxel.

---

## 2.6 Expanded Bounding Box

Source: [`SimpleNodePlacer._expanded_box_voxels()`](../../router-layer/placement/simple_node_placer.py:172)

Each node has a voxel extent `(ex, ey, ez)` (default `(1,1,1)` for simple
nodes; larger for equipment). The expanded box adds a clearance margin:

```
box_min[i] = anchor[i] - floor(extent[i] / 2) - clearance
box_max[i] = anchor[i] + floor(extent[i] / 2) + clearance
```

The box must satisfy:
- `box_min[i] >= 0` and `box_max[i] < grid_dim[i]` (in-bounds)
- No voxel in the box is already occupied

---

## 2.7 PlacedNode World Coordinate

Once an anchor voxel `(vx, vy, vz)` is found:

```
wc = vc_to_wc(anchor_vc, config)
   = (origin_x + (vx + 0.5) × vs,
      origin_y + (vy + 0.5) × vs,
      origin_z + (vz + 0.5) × vs)
```

This is the **voxel centre** in world space.

---

## 2.8 Equipment Port Shell Snapping

Source: [`EquipmentPortShellSnapper`](../../router-layer/snapping/shell_snapper.py:15)

Signal ports (role `"signal"`, `port_kind = "instrument_tap"`, or
`snap_to_shell = true`) that belong to a tank are snapped onto the cylindrical
shell of that tank after initial placement.

**Step 1 — Resolve tank centre.**
The base port (non-signal port of the same equipment) gives the tank anchor
voxel. The tank centre in world space is:

```
tank_center_wc = compute_tank_wc_center(base_port_wc)
```

(shifts the base port wc upward by half the tank height to find the geometric
centre of the cylinder).

**Step 2 — Radial snap.**
Given the port's current world position `wc` and the tank centre `center_wc`:

```
dx = wc[0] - center_wc[0]
dy = wc[1] - center_wc[1]
radial_len = sqrt(dx² + dy²)

# Project onto shell surface at radius shell_radius:
sx = center_wc[0] + shell_radius × dx / radial_len
sy = center_wc[1] + shell_radius × dy / radial_len

# Clamp Z to tank height:
sz = clamp(wc[2], center_wc[2] - shell_height/2, center_wc[2] + shell_height/2)

snapped_wc = (sx, sy, sz)
```

If `radial_len < 1e-9` (port is exactly at the tank axis), the direction
defaults to `(1, 0)`.

**Step 3 — Re-snap to voxel grid.**
The snapped world coordinate is converted back to a voxel index and then
re-converted to the voxel centre:

```
snapped_vc = wc_to_vc(snapped_wc)
snapped_wc_exact = vc_to_wc(snapped_vc, config)
```

This ensures the placed node always sits at a voxel centre.
