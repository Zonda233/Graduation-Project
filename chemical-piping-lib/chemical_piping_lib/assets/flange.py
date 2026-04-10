"""
flange.py
=========
Pipe flange asset — an annular disc with optional bolt holes.

Flanges are not independent JSON components; they are created automatically
when a Pipe or segment has ``with_flanges: true``, or when a Tank port
specifies a ``flange_spec``.  However the class is also directly
instantiable for testing.

JSON-equivalent comp_data keys
-------------------------------
``comp_id``          — unique id string
``wc_face``          — world-space position of the flange *face* (the
                       surface that mates with the pipe end)
``face_axis``        — outward normal direction string (e.g. ``"+Z"``)
``nominal_diameter`` — nominal pipe diameter in metres

Geometry strategy
-----------------
1. Build flange outer disc (solid cylinder) with bmesh.
2. Build inner bore cylinder (solid).
3. Use :func:`boolean_utils.boolean_difference` to cut the bore from the disc.
4. Optionally drill bolt holes with repeated boolean differences.

The flange face is at z=0 in local space; the flange body extends in the
**negative Z** direction.  After construction the object is rotated so that
its local +Z aligns with ``face_axis``, and translated so that the face sits
exactly at ``wc_face``.
"""

from __future__ import annotations

import logging
import math

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import (
    FLANGE_SHOW_BOLTS,
    RUNTIME,
    get_dn_spec,
    get_flange_spec,
)
from chemical_piping_lib.utils.bmesh_utils import bm_to_object, make_cylinder, recalc_normals
from chemical_piping_lib.utils.boolean_utils import boolean_difference
from chemical_piping_lib.utils.coords import align_object_to_axis, axis_to_vec
from chemical_piping_lib.utils.ops_wrapper import delete_object

from .base import PipingAsset

log = logging.getLogger(__name__)


class Flange(PipingAsset):
    """
    An annular pipe flange.

    Parameters
    ----------
    comp_data:
        Dict with ``comp_id``, ``wc_face``, ``face_axis``,
        ``nominal_diameter``.
    spec:
        Spec dict with at least ``nominal_diameter``.
    material_id:
        Material key (typically ``"flange"``).
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

        self.wc_face   = Vector(comp_data["wc_face"])
        self.face_axis: str = comp_data["face_axis"]
        nominal_d      = float(
            comp_data.get("nominal_diameter") or spec.get("nominal_diameter", 0.1)
        )

        # Pipe bore geometry.
        dn_spec = get_dn_spec(nominal_d)
        self.bore_radius: float    = dn_spec["outer_diameter"] / 2.0

        # Flange plate geometry.
        fl_spec = get_flange_spec(nominal_d)
        self.outer_radius: float   = float(fl_spec["outer_diameter"]) / 2.0
        self.thickness: float      = float(fl_spec["thickness"])
        self.bolt_count: int       = int(fl_spec["bolt_count"])
        self.bolt_circle_r: float  = float(fl_spec["bolt_circle_d"]) / 2.0
        self.bolt_hole_r: float    = float(fl_spec["bolt_hole_d"]) / 2.0

    # ------------------------------------------------------------------
    # PipingAsset interface
    # ------------------------------------------------------------------

    def build(self) -> bpy.types.Object:
        log.debug("Flange.build: %s  face=%s  axis=%s", self.comp_id, self.wc_face, self.face_axis)

        # --- 1. Flange disc (solid cylinder, local +Z = outward face) -
        bm = bmesh.new()
        # Place disc so its TOP face (z = +thickness/2 from centre) is the
        # mating face.  We will shift the object later.
        make_cylinder(
            bm,
            radius=self.outer_radius,
            depth=self.thickness,
            segments=RUNTIME.mesh_segments,
        )
        recalc_normals(bm)
        disc_obj = bm_to_object(bm, name=f"{self.comp_id}_disc", collection=self.collection)

        # --- 2. Bore cylinder (cutter) --------------------------------
        bm2 = bmesh.new()
        make_cylinder(
            bm2,
            radius=self.bore_radius,
            depth=self.thickness + 0.002,   # slightly over-sized to avoid z-fighting
            segments=RUNTIME.mesh_segments,
        )
        recalc_normals(bm2)
        bore_obj = bm_to_object(bm2, name=f"{self.comp_id}_bore", collection=self.collection)

        # --- 3. Boolean: disc - bore ----------------------------------
        boolean_difference(disc_obj, bore_obj, keep_cutter=False)
        # bore_obj deleted by boolean_difference

        # --- 4. Optional bolt holes -----------------------------------
        if FLANGE_SHOW_BOLTS:
            self._drill_bolt_holes(disc_obj)

        # --- 5. Rotate & translate to world position ------------------
        align_object_to_axis(disc_obj, self.face_axis)

        # The flange face should sit at wc_face.  In local space the top
        # of the cylinder (the mating face) is at +thickness/2 from centre.
        # After rotation this offset is along face_axis direction.
        face_dir = axis_to_vec(self.face_axis)
        disc_obj.location = self.wc_face - face_dir * (self.thickness / 2.0)

        # --- 6. Rename final object to comp_id -----------------------
        disc_obj.name      = self.comp_id
        disc_obj.data.name = self.comp_id
        self._obj          = disc_obj

        self._finalise()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """Return the single mating face centre."""
        return {"face": self.wc_face.copy()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _drill_bolt_holes(self, flange_obj: bpy.types.Object) -> None:
        """
        Subtract ``bolt_count`` equally-spaced cylindrical holes from
        *flange_obj* arranged on the bolt-circle diameter.
        """
        for i in range(self.bolt_count):
            angle = 2.0 * math.pi * i / self.bolt_count
            bx = self.bolt_circle_r * math.cos(angle)
            by = self.bolt_circle_r * math.sin(angle)

            bm = bmesh.new()
            make_cylinder(
                bm,
                radius=self.bolt_hole_r,
                depth=self.thickness + 0.002,
                segments=16,       # bolt holes can be lower resolution
            )
            recalc_normals(bm)
            hole_obj = bm_to_object(
                bm,
                name=f"{self.comp_id}_bolt{i}",
                collection=self.collection,
            )
            hole_obj.location = Vector((bx, by, 0.0))

            from chemical_piping_lib.utils.boolean_utils import boolean_difference
            boolean_difference(flange_obj, hole_obj, keep_cutter=False)
