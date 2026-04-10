"""
pipe.py
=======
Straight pipe segment asset.

JSON component schema (excerpt)
--------------------------------
.. code-block:: json

    {
        "comp_id"  : "seg01_c01",
        "type"     : "Pipe",
        "wc_start" : [0.7, 0.7, 0.0],
        "wc_end"   : [0.7, 0.7, 0.6],
        "axis"     : "+Z",
        "length_m" : 0.6
    }

Geometry strategy
-----------------
* Solid cylinder  (when ``config.PIPE_HOLLOW`` is ``False``): fast, looks
  fine at voxel scale.
* Hollow tube     (when ``config.PIPE_HOLLOW`` is ``True``): wall thickness
  comes from the DN table.

The cylinder is built along the **+Z** canonical axis and then rotated to
its target ``axis`` direction.  Its centre is placed at the midpoint of
``wc_start`` and ``wc_end``.

Optional flanges
----------------
If ``spec["with_flanges"]`` is ``True``, :class:`Flange` objects are
automatically instantiated at both ends.  They are built as separate Blender
objects linked to the same collection, not merged into the pipe mesh.
This keeps each asset's mesh clean and manifold.
"""

from __future__ import annotations

import logging

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import PIPE_HOLLOW, RUNTIME, get_dn_spec
from chemical_piping_lib.utils.bmesh_utils import (
    bm_to_object,
    make_cylinder,
    make_tube,
    recalc_normals,
)
from chemical_piping_lib.utils.coords import (
    align_object_to_axis,
    axis_to_vec,
    midpoint,
)

from .base import PipingAsset

log = logging.getLogger(__name__)


class Pipe(PipingAsset):
    """
    A straight, axis-aligned pipe segment.

    Parameters
    ----------
    comp_data:
        Component dict from the JSON ``segments[].components[]`` array.
        Must contain ``wc_start``, ``wc_end``, ``axis``, ``length_m``.
    spec:
        Parent segment ``spec`` dict.  Must contain ``nominal_diameter``
        and optionally ``with_flanges`` (default ``False``).
    material_id:
        Material key (e.g. ``"carbon_steel"``).
    collection:
        Optional target Blender collection.
    """

    def __init__(
        self,
        comp_data:   dict,
        spec:        dict,
        material_id: str,
        collection=None,
    ) -> None:
        super().__init__(comp_data, spec, material_id, collection)

        # Parse and validate required fields.
        self.wc_start  = Vector(comp_data["wc_start"])
        self.wc_end    = Vector(comp_data["wc_end"])
        self.axis: str = comp_data["axis"]
        self.length_m  = float(comp_data["length_m"])

        # Resolve pipe geometry from DN spec.
        nominal_d  = float(spec["nominal_diameter"])
        dn_spec    = get_dn_spec(nominal_d)
        self.outer_radius: float = dn_spec["outer_diameter"] / 2.0
        self.wall_thickness: float = dn_spec["wall_thickness"]

        self.with_flanges: bool = bool(spec.get("with_flanges", False))

    # ------------------------------------------------------------------
    # PipingAsset interface
    # ------------------------------------------------------------------

    def build(self) -> bpy.types.Object:
        """
        Construct the pipe cylinder and optional flanges.

        Returns
        -------
        The pipe ``bpy.types.Object``.
        """
        log.debug("Pipe.build: %s  axis=%s  length=%.3f m", self.comp_id, self.axis, self.length_m)

        # --- 1. Build geometry ----------------------------------------
        bm = bmesh.new()

        if PIPE_HOLLOW:
            make_tube(
                bm,
                radius=self.outer_radius,
                depth=self.length_m,
                wall_thickness=self.wall_thickness,
                segments=RUNTIME.mesh_segments,
            )
        else:
            make_cylinder(
                bm,
                radius=self.outer_radius,
                depth=self.length_m,
                segments=RUNTIME.mesh_segments,
            )

        recalc_normals(bm)

        # --- 2. Write bmesh → Object (at world origin, along +Z) ------
        self._obj = bm_to_object(bm, name=self.comp_id, collection=self.collection)

        # --- 3. Rotate to target axis ---------------------------------
        align_object_to_axis(self._obj, self.axis)

        # --- 4. Move to midpoint of the segment -----------------------
        self._obj.location = midpoint(self.wc_start, self.wc_end)

        # --- 5. Finalise (material + collection linkage) --------------
        self._finalise()

        # --- 6. Optional flanges -------------------------------------
        if self.with_flanges:
            self._add_flanges()

        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """
        Return the two end-points of the pipe.

        Returns
        -------
        ``{"start": Vector, "end": Vector}``
        """
        return {
            "start": self.wc_start.copy(),
            "end":   self.wc_end.copy(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_flanges(self) -> None:
        """
        Instantiate a :class:`flange.Flange` at each end of the pipe.

        The flanges are built as independent objects linked to the same
        collection.  Their face normals point outward (away from the pipe
        centre).
        """
        # Import here to avoid circular imports at module level.
        from chemical_piping_lib.assets.flange import Flange

        nominal_d = float(self.spec["nominal_diameter"])

        for port_name, wc, face_axis in [
            ("start", self.wc_start, _opposite_axis(self.axis)),
            ("end",   self.wc_end,   self.axis),
        ]:
            flange_id = f"{self.comp_id}_flange_{port_name}"
            flange_data = {
                "comp_id":           flange_id,
                "wc_face":           list(wc),
                "face_axis":         face_axis,
                "nominal_diameter":  nominal_d,
            }
            flange_spec = {"nominal_diameter": nominal_d}
            f = Flange(
                comp_data=flange_data,
                spec=flange_spec,
                material_id="flange",
                collection=self.collection,
            )
            f.build()
            log.debug("Pipe._add_flanges: built flange %r at %s.", flange_id, port_name)


# ---------------------------------------------------------------------------
# Module-level helper (avoids importing config.AXIS_OPPOSITE into every file)
# ---------------------------------------------------------------------------

def _opposite_axis(axis: str) -> str:
    """Return the axis string pointing in the opposite direction."""
    return {
        "+X": "-X", "-X": "+X",
        "+Y": "-Y", "-Y": "+Y",
        "+Z": "-Z", "-Z": "+Z",
    }[axis]
