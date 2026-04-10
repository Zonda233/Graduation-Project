"""
valve.py
========
Valve asset — a visually recognisable occupancy placeholder.

In the voxel-scale overview model, valves do not need precise internal
geometry.  What matters is:

* Correct position and axis alignment.
* Visually distinct appearance (different colour / shape from pipe).
* Two well-defined end-ports that line up with adjacent pipe segments.

Supported subtypes
------------------
``Gate``
    Cylindrical body with a raised bonnet (vertical stub on top).
    Represents a gate valve (wedge disc, rising stem).

``Ball``
    Sphere body with short end stubs and a side handle tab.
    Represents a ball valve.

JSON component schema (excerpt)
--------------------------------
.. code-block:: json

    {
        "comp_id"          : "seg01_c04",
        "type"             : "Valve",
        "subtype"          : "Gate",
        "wc_start"         : [1.3, 0.7, 0.6],
        "wc_end"           : [1.7, 0.7, 0.6],
        "axis"             : "+X",
        "nominal_diameter" : 0.1
    }

Geometry strategy
-----------------
All parts are built as separate bmesh objects and joined with
:func:`ops_wrapper.join_objects` at the end.
"""

from __future__ import annotations

import logging

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import RUNTIME, get_dn_spec
from chemical_piping_lib.utils.bmesh_utils import (
    bm_to_object,
    make_cylinder,
    recalc_normals,
)
from chemical_piping_lib.utils.coords import align_object_to_axis, axis_to_vec, midpoint
from chemical_piping_lib.utils.ops_wrapper import join_objects

from .base import PipingAsset

log = logging.getLogger(__name__)

# Valve body proportions relative to pipe outer diameter.
_BODY_LENGTH_FACTOR  = 2.0   # valve body length = 2 × OD
_BODY_RADIUS_FACTOR  = 1.4   # valve body radius = 1.4 × pipe OD
_BONNET_LENGTH       = 0.06  # gate bonnet height (metres)
_BONNET_RADIUS_RATIO = 0.5   # bonnet radius = 0.5 × body radius
_HANDLE_LENGTH       = 0.08  # ball valve handle length
_HANDLE_THICKNESS    = 0.01  # ball valve handle thickness


class Valve(PipingAsset):
    """
    Gate or Ball valve.

    Parameters
    ----------
    comp_data:
        Component dict.  Required: ``wc_start``, ``wc_end``, ``axis``.
        Optional: ``subtype`` (``"Gate"`` | ``"Ball"``; default ``"Gate"``),
        ``nominal_diameter`` (overrides spec if present).
    spec:
        Segment spec dict.  Must contain ``nominal_diameter``.
    material_id:
        Material key (typically ``"valve_body"``).
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

        self.wc_start  = Vector(comp_data["wc_start"])
        self.wc_end    = Vector(comp_data["wc_end"])
        self.axis: str = comp_data["axis"]
        self.subtype: str = comp_data.get("subtype", "Gate")

        nominal_d = float(
            comp_data.get("nominal_diameter") or spec.get("nominal_diameter", 0.1)
        )
        dn_spec = get_dn_spec(nominal_d)
        self.pipe_radius: float = dn_spec["outer_diameter"] / 2.0
        self.body_radius: float = self.pipe_radius * _BODY_RADIUS_FACTOR
        # Span the full segment so valve butts against adjacent pipes (no gap).
        segment_length = (self.wc_end - self.wc_start).length
        min_length = self.pipe_radius * 2 * _BODY_LENGTH_FACTOR
        self.body_length: float = max(segment_length, min_length)

    # ------------------------------------------------------------------
    # PipingAsset interface
    # ------------------------------------------------------------------

    def build(self) -> bpy.types.Object:
        log.debug(
            "Valve.build: %s  subtype=%s  axis=%s",
            self.comp_id, self.subtype, self.axis,
        )

        if self.subtype == "Ball":
            base_obj, extras = self._build_ball()
        else:
            base_obj, extras = self._build_gate()

        # Join all parts into one object.
        self._obj = join_objects(base_obj, extras)
        self._obj.name      = self.comp_id
        self._obj.data.name = self.comp_id

        # Rotate then translate to world position.
        align_object_to_axis(self._obj, self.axis)
        self._obj.location = midpoint(self.wc_start, self.wc_end)

        self._finalise()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        return {
            "start": self.wc_start.copy(),
            "end":   self.wc_end.copy(),
        }

    # ------------------------------------------------------------------
    # Gate valve geometry
    # ------------------------------------------------------------------

    def _build_gate(self) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
        """
        Build a gate-valve placeholder.

        Shape: cylindrical body + cylindrical bonnet stub on top.
        All parts built along local +Z (will be rotated in build()).
        """
        extras: list[bpy.types.Object] = []

        # Body.
        bm = bmesh.new()
        make_cylinder(bm, radius=self.body_radius, depth=self.body_length,
                      segments=RUNTIME.mesh_segments)
        recalc_normals(bm)
        body = bm_to_object(bm, f"{self.comp_id}_body", self.collection)

        # Bonnet (vertical stub, sits at +body_radius in local Y after rotation).
        # In local space before rotation: extends along +Z from body centre.
        bm2 = bmesh.new()
        bonnet_r = self.body_radius * _BONNET_RADIUS_RATIO
        make_cylinder(bm2, radius=bonnet_r, depth=_BONNET_LENGTH,
                      segments=RUNTIME.mesh_segments)
        recalc_normals(bm2)
        bonnet = bm_to_object(bm2, f"{self.comp_id}_bonnet", self.collection)
        # Offset bonnet to sit on top of the body (local +Y before rotation).
        # After rotation to axis direction, +Y becomes the side perpendicular
        # to the flow — which is where the handwheel should be.
        bonnet.location = Vector((0.0, self.body_radius + _BONNET_LENGTH / 2.0, 0.0))
        extras.append(bonnet)

        return body, extras

    # ------------------------------------------------------------------
    # Ball valve geometry
    # ------------------------------------------------------------------

    def _build_ball(self) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
        """
        Build a ball-valve placeholder.

        Shape: sphere body (radius = body_length/2 so it spans wc_start..wc_end)
        + flat handle tab on side.
        """
        extras: list[bpy.types.Object] = []

        # Sphere radius = half of segment length so the sphere touches both ports.
        ball_radius = self.body_length / 2.0

        mesh = bpy.data.meshes.new(f"{self.comp_id}_ball_mesh")
        body = bpy.data.objects.new(f"{self.comp_id}_body", mesh)
        col = self.collection or bpy.context.scene.collection
        col.objects.link(body)

        bm = bmesh.new()
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=RUNTIME.mesh_segments,
            v_segments=RUNTIME.mesh_segments // 2,
            radius=ball_radius,
        )
        recalc_normals(bm)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        # Handle tab (flat box, local +Y side).
        handle = self._make_handle_box()
        handle.location = Vector((0.0, ball_radius + _HANDLE_LENGTH / 2.0, 0.0))
        extras.append(handle)

        return body, extras

    def _make_handle_box(self) -> bpy.types.Object:
        """Create a small flat rectangular handle mesh."""
        mesh = bpy.data.meshes.new(f"{self.comp_id}_handle_mesh")
        obj  = bpy.data.objects.new(f"{self.comp_id}_handle", mesh)
        col  = self.collection or bpy.context.scene.collection
        col.objects.link(obj)

        bm = bmesh.new()
        # bmesh box: use create_cube scaled to handle proportions.
        bmesh.ops.create_cube(bm, size=1.0)
        # Scale: X = body_length/2 (span across flow), Y = handle depth, Z = thickness
        sx = self.body_length * 0.5
        sy = _HANDLE_LENGTH
        sz = _HANDLE_THICKNESS
        bmesh.ops.scale(bm, vec=Vector((sx, sy, sz)), verts=bm.verts)
        recalc_normals(bm)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        return obj
