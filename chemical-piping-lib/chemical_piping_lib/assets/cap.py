"""
cap.py
======
Pipe cap (blind end) asset — closes the end of a pipe run.

JSON component schema (excerpt)
--------------------------------
.. code-block:: json

    {
        "comp_id":  "seg01_c05",
        "type":     "Cap",
        "wc":       [2.1, 0.7, 0.7],
        "axis":     "+X"
    }

The *wc* is the mating face (where the pipe connects). The cap extends
in the direction of *axis* (the closed/bulge side).

Geometry strategy
-----------------
A short solid cylinder with one end at the mating face and the other
end capped (closed). Built along +Z then rotated so that the mating
face (local z=0) is at *wc* and the cap extends in *axis* direction.
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
from chemical_piping_lib.utils.coords import align_object_to_axis, axis_to_vec

from .base import PipingAsset

log = logging.getLogger(__name__)


# Cap body length (metres) — short stub that closes the pipe end.
CAP_DEPTH_DEFAULT = 0.04


class Cap(PipingAsset):
    """
    A pipe cap (blind flange / pipe end closure).

    Parameters
    ----------
    comp_data:
        Component dict.  Required: ``wc``, ``axis``.
    spec:
        Parent segment spec.  Must contain ``nominal_diameter`` for cap radius.
    material_id:
        Material key.
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

        self.wc    = Vector(comp_data["wc"])
        self.axis: str = comp_data["axis"]

        nominal_d = float(spec.get("nominal_diameter", 0.1))
        dn_spec   = get_dn_spec(nominal_d)
        self.outer_radius = dn_spec["outer_diameter"] / 2.0
        # Cap depth: short stub; use segment nominal or default.
        self.depth = CAP_DEPTH_DEFAULT

    def build(self) -> bpy.types.Object:
        """
        Build a short closed cylinder. Mating face at local z=0, cap at z=depth.
        """
        log.debug("Cap.build: %s  axis=%s  R=%.3f m", self.comp_id, self.axis, self.outer_radius)

        bm = bmesh.new()
        # Cylinder centered at (0,0,depth/2) so one face at z=0, one at z=depth.
        make_cylinder(
            bm,
            radius=self.outer_radius,
            depth=self.depth,
            segments=RUNTIME.mesh_segments,
            center=Vector((0.0, 0.0, self.depth * 0.5)),
        )
        recalc_normals(bm)
        self._obj = bm_to_object(bm, name=self.comp_id, collection=self.collection)
        align_object_to_axis(self._obj, self.axis)
        # Mating face (local z=0) at wc.
        self._obj.location = self.wc.copy()
        self._finalise()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """
        Cap has a single "face" port (the mating point where the pipe connects).
        """
        return {"face": self.wc.copy()}
