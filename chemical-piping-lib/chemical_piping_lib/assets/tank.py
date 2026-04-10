"""
tank.py
=======
Storage tank asset (vertical or horizontal, with ellipsoidal heads).

JSON asset schema (excerpt)
----------------------------
.. code-block:: json

    {
        "id"          : "tank_01",
        "type"        : "Tank",
        "voxel_origin": [2, 2, 0],
        "voxel_extent": [3, 3, 6],
        "geometry": {
            "shell_radius"  : 0.5,
            "shell_height"  : 0.8,
            "head_type"     : "ellipsoidal",
            "orientation"   : "vertical"
        },
        "material_id" : "stainless_steel",
        "ports": [
            {
                "port_id"          : "tank_01_nozzle_top",
                "role"             : "inlet",
                "vc"               : [3, 3, 6],
                "wc"               : [0.7, 0.7, 1.2],
                "direction"        : "+Z",
                "nominal_diameter" : 0.1
            }
        ]
    }

Geometry strategy
-----------------
* **Shell**: solid cylinder (bmesh).
* **Heads**: two UV-spheres scaled to 2:1 ellipsoid (bmesh.ops.create_uvsphere
  + scale), one per end cap.  Each head is joined to the shell via
  :func:`ops_wrapper.join_objects`.
* **Nozzles**: short stub cylinders extruded from the shell surface, one per
  port definition.  A Flange is optionally added at the nozzle tip if
  ``flange_spec`` is present in the port definition.
* **Orientation**: if ``"horizontal"``, the finished object is rotated 90°
  around the X-axis.

2:1 Ellipsoidal head approximation
-----------------------------------
A UV sphere of radius ``R`` is created and its Z-scale set to ``0.5``.
This gives a semi-axis of ``R`` (equatorial) and ``0.5R`` (polar), matching
the 2:1 ellipsoidal head standard (ASME Section VIII / GB 150).
"""

from __future__ import annotations

import logging
import math

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import NOZZLE_LENGTH, RUNTIME, get_dn_spec
from chemical_piping_lib.utils.bmesh_utils import (
    bm_to_object,
    make_cylinder,
    recalc_normals,
    remove_doubles,
)
from chemical_piping_lib.utils.coords import (
    align_object_to_axis,
    axis_to_vec,
    vc_to_wc_point,
)
from chemical_piping_lib.utils.ops_wrapper import join_objects

from .base import PipingAsset

log = logging.getLogger(__name__)


class Tank(PipingAsset):
    """
    A storage vessel (vertical or horizontal cylindrical tank).

    Parameters
    ----------
    comp_data:
        The asset dict from ``json_data["assets"]``.
        Required keys: ``id``, ``geometry``, ``ports``.
        Optional: ``voxel_origin``, ``voxel_extent``, ``material_id``.
    spec:
        Pass an empty dict ``{}``; Tank reads its own spec from
        ``comp_data["geometry"]``.
    material_id:
        Material key (e.g. ``"stainless_steel"``).
    collection:
        Optional target collection.
    """

    def __init__(
        self,
        comp_data:   dict,
        spec:        dict,
        material_id: str,
        collection=None,
    ) -> None:
        super().__init__(comp_data, spec, material_id, collection)

        geom = comp_data.get("geometry", {})
        self.shell_radius: float  = float(geom.get("shell_radius", 0.5))
        self.shell_height: float  = float(geom.get("shell_height", 1.0))
        self.head_type: str       = geom.get("head_type", "ellipsoidal")
        self.orientation: str     = geom.get("orientation", "vertical")

        # Port definitions from JSON.
        self.ports_def: list[dict] = comp_data.get("ports", [])

        # World centre can be given explicitly. Otherwise derive it from the
        # voxel bounding box centre expressed in voxel-grid coordinates.
        if "wc_center" in comp_data:
            self.world_center = Vector(comp_data["wc_center"])
        else:
            vo = comp_data.get("voxel_origin")
            ve = comp_data.get("voxel_extent")
            if vo and ve:
                cx = vo[0] + ve[0] / 2.0
                cy = vo[1] + ve[1] / 2.0
                cz = vo[2] + ve[2] / 2.0
                self.world_center = vc_to_wc_point([cx, cy, cz])
            else:
                self.world_center = Vector((0.0, 0.0, 0.0))

        # Map port_id → world position (populated in build).
        self._port_positions: dict[str, Vector] = {}

    # ------------------------------------------------------------------
    # PipingAsset interface
    # ------------------------------------------------------------------

    def build(self) -> bpy.types.Object:
        log.debug(
            "Tank.build: %s  R=%.3f H=%.3f  head=%s  orient=%s",
            self.comp_id, self.shell_radius, self.shell_height,
            self.head_type, self.orientation,
        )

        parts: list[bpy.types.Object] = []

        # --- 1. Shell cylinder (at local origin) ----------------------
        bm = bmesh.new()
        make_cylinder(
            bm,
            radius=self.shell_radius,
            depth=self.shell_height,
            segments=RUNTIME.mesh_segments,
        )
        recalc_normals(bm)
        shell = bm_to_object(bm, f"{self.comp_id}_shell", self.collection)

        # --- 2. Heads (at local offsets) ------------------------------
        head_top, head_bot = self._build_heads()

        half_h = self.shell_height / 2.0
        head_top.location = Vector((0.0, 0.0,  half_h))
        head_bot.location = Vector((0.0, 0.0, -half_h))

        parts.extend([head_top, head_bot])

        # --- 3. Nozzles (at local offsets, NOT world coords) ----------
        nozzle_objs = self._build_nozzles_local()
        parts.extend(nozzle_objs)

        # --- 4. Join everything into shell ----------------------------
        self._obj = join_objects(shell, parts)
        self._obj.name      = self.comp_id
        self._obj.data.name = self.comp_id

        bm_clean = bmesh.new()
        bm_clean.from_mesh(self._obj.data)
        remove_doubles(bm_clean, dist=1e-5)
        recalc_normals(bm_clean)
        bm_clean.to_mesh(self._obj.data)
        bm_clean.free()
        self._obj.data.update()

        # --- 5. Orientation ------------------------------------------
        if self.orientation == "horizontal":
            self._obj.rotation_euler[0] = math.pi / 2.0

        # --- 6. Translate assembled tank to world centre (LAST step) --
        self._obj.location = self.world_center

        # --- 7. Finalise ---------------------------------------------
        self._finalise()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        return {k: v.copy() for k, v in self._port_positions.items()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _head_height(self) -> float:
        """
        Return the axial height of one head cap.

        * ellipsoidal  : R / 2  (2:1 ellipsoidal standard)
        * hemispherical: R
        * flat         : 0  (no separate cap object; shell cap suffices)
        """
        if self.head_type == "ellipsoidal":
            return self.shell_radius / 2.0
        if self.head_type == "hemispherical":
            return self.shell_radius
        return 0.0  # flat

    def _build_heads(
        self,
    ) -> tuple[bpy.types.Object, bpy.types.Object]:
        """
        Build two head cap objects (top and bottom).

        Returns ``(head_top, head_bot)`` — Blender Objects not yet positioned.
        For ``"flat"`` heads, dummy zero-geometry objects are returned so
        the caller's logic stays uniform.
        """
        col = self.collection or bpy.context.scene.collection

        if self.head_type == "flat":
            # Flat heads are already included in the shell end-caps;
            # return empty mesh objects as placeholders.
            def _empty(name):
                m = bpy.data.meshes.new(name)
                o = bpy.data.objects.new(name, m)
                col.objects.link(o)
                return o
            return _empty(f"{self.comp_id}_head_top"), _empty(f"{self.comp_id}_head_bot")

        def _make_head(name: str) -> bpy.types.Object:
            mesh = bpy.data.meshes.new(name)
            obj  = bpy.data.objects.new(name, mesh)
            col.objects.link(obj)

            bm = bmesh.new()
            bmesh.ops.create_uvsphere(
                bm,
                u_segments=RUNTIME.mesh_segments,
                v_segments=RUNTIME.mesh_segments // 2,
                radius=self.shell_radius,
            )

            if self.head_type == "ellipsoidal":
                # Scale Z to 0.5 → 2:1 ellipsoidal head.
                bmesh.ops.scale(
                    bm,
                    vec=Vector((1.0, 1.0, 0.5)),
                    verts=bm.verts,
                )

            # Keep only the upper hemisphere (Z >= 0).
            to_delete = [f for f in bm.faces if f.calc_center_median().z < 0.0]
            bmesh.ops.delete(bm, geom=to_delete, context='FACES')

            # Re-cap the open bottom ring with an n-gon.
            bm.edges.ensure_lookup_table()
            boundary_edges = [e for e in bm.edges if e.is_boundary]
            if boundary_edges:
                bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)

            recalc_normals(bm)
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
            return obj

        top = _make_head(f"{self.comp_id}_head_top")
        # Bottom head: same shape, flipped 180°.
        bot = _make_head(f"{self.comp_id}_head_bot")
        bot.rotation_euler[0] = math.pi   # flip upside-down

        return top, bot

    def _build_nozzles_local(self) -> list[bpy.types.Object]:
        """
        Build nozzle stubs in the **tank's local coordinate system** (origin
        at tank centre, +Z up).  Record port positions in **world space** so
        downstream pipe segments can use them directly.
        """
        from chemical_piping_lib.assets.flange import Flange

        nozzle_objs: list[bpy.types.Object] = []

        for port in self.ports_def:
            port_id  = port["port_id"]
            direction: str = port["direction"]
            nominal_d: float = float(port.get("nominal_diameter", 0.05))

            local_root = self._port_local_offset(port)

            dn_spec    = get_dn_spec(nominal_d)
            nozzle_r   = dn_spec["outer_diameter"] / 2.0
            nozzle_len = float(port.get("nozzle_length_m", NOZZLE_LENGTH))
            dir_vec    = axis_to_vec(direction)

            bm = bmesh.new()
            make_cylinder(bm, radius=nozzle_r, depth=nozzle_len,
                          segments=RUNTIME.mesh_segments)
            recalc_normals(bm)
            nozzle_obj = bm_to_object(
                bm,
                name=f"{self.comp_id}_{port_id}_nozzle",
                collection=self.collection,
            )
            align_object_to_axis(nozzle_obj, direction)
            nozzle_obj.location = local_root + dir_vec * (nozzle_len / 2.0)
            nozzle_objs.append(nozzle_obj)

            world_root = self.world_center + local_root
            tip_wc     = world_root + dir_vec * nozzle_len
            self._port_positions[port_id] = tip_wc

            if "flange_spec" in port:
                fl_data = {
                    "comp_id":          f"{port_id}_flange",
                    "wc_face":          list(tip_wc),
                    "face_axis":        direction,
                    "nominal_diameter": nominal_d,
                }
                fl = Flange(
                    comp_data=fl_data,
                    spec={"nominal_diameter": nominal_d},
                    material_id="flange",
                    collection=self.collection,
                )
                fl.build()

        return nozzle_objs

    def _port_local_offset(self, port: dict) -> Vector:
        """
        Return the nozzle attachment point as a **local offset** from the
        tank centre (0, 0, 0).

        If the JSON provides ``wc``, convert it to local by subtracting
        ``world_center``.  Otherwise derive from geometry + direction.
        """
        if "wc" in port:
            return Vector(port["wc"]) - self.world_center

        direction = port["direction"]
        half_h = self.shell_height / 2.0
        head_h = self._head_height()

        offsets = {
            "+X": Vector(( self.shell_radius, 0.0, 0.0)),
            "-X": Vector((-self.shell_radius, 0.0, 0.0)),
            "+Y": Vector((0.0,  self.shell_radius, 0.0)),
            "-Y": Vector((0.0, -self.shell_radius, 0.0)),
            "+Z": Vector((0.0, 0.0,  half_h + head_h)),
            "-Z": Vector((0.0, 0.0, -half_h - head_h)),
        }
        if direction in offsets:
            return offsets[direction]

        raise ValueError(
            f"Tank {self.comp_id!r}: port {port.get('port_id', '?')!r} has "
            f"unsupported direction {direction!r} for automatic placement."
        )
