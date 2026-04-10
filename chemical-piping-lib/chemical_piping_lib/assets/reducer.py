"""
reducer.py
==========
Reducer (concentric pipe reducer) asset — connects two pipe sizes.

JSON component schema (excerpt)
-------------------------------
.. code-block:: json

    {
        "comp_id":         "seg01_c04",
        "type":            "Reducer",
        "wc_start":        [1.7, 0.7, 0.7],
        "wc_end":          [1.9, 0.7, 0.7],
        "axis":            "+X",
        "diameter_in_m":   0.1,
        "diameter_out_m":  0.05
    }

Geometry strategy
-----------------
A solid frustum (truncated cone) between the two end radii. Radii are taken
from the DN table via the nominal diameters. Built along +Z then rotated
to the target axis and placed at the segment midpoint.
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
    make_frustum,
    recalc_normals,
)
from chemical_piping_lib.utils.coords import (
    align_object_to_axis,
    axis_to_vec,
    midpoint,
)

from .base import PipingAsset

log = logging.getLogger(__name__)


class Reducer(PipingAsset):
    """
    A concentric reducer (transition between two pipe diameters).

    Parameters
    ----------
    comp_data:
        Component dict.  Required: ``wc_start``, ``wc_end``, ``axis``,
        ``diameter_in_m``, ``diameter_out_m``.
    spec:
        Parent segment spec (for material; nominal_diameter not used for radii).
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

        self.wc_start = Vector(comp_data["wc_start"])
        self.wc_end   = Vector(comp_data["wc_end"])
        self.axis: str = comp_data["axis"]
        self.diameter_in_m  = float(comp_data["diameter_in_m"])
        self.diameter_out_m = float(comp_data["diameter_out_m"])

        dn_in  = get_dn_spec(self.diameter_in_m)
        dn_out = get_dn_spec(self.diameter_out_m)
        self.radius_in  = dn_in["outer_diameter"] / 2.0
        self.radius_out = dn_out["outer_diameter"] / 2.0
        self.length_m   = (self.wc_end - self.wc_start).length

    def build(self) -> bpy.types.Object:
        """Build the frustum (or cylinder if same diameter)."""
        log.debug(
            "Reducer.build: %s  axis=%s  %.3f→%.3f m  length=%.3f m",
            self.comp_id, self.axis, self.diameter_in_m, self.diameter_out_m, self.length_m,
        )

        bm = bmesh.new()

        # Inlet at -Z half, outlet at +Z half in local space.
        if abs(self.radius_in - self.radius_out) < 1e-9:
            make_cylinder(
                bm,
                radius=self.radius_in,
                depth=self.length_m,
                segments=RUNTIME.mesh_segments,
            )
        else:
            make_frustum(
                bm,
                radius_bottom=self.radius_in,
                radius_top=self.radius_out,
                depth=self.length_m,
                segments=RUNTIME.mesh_segments,
            )

        recalc_normals(bm)
        self._obj = bm_to_object(bm, name=self.comp_id, collection=self.collection)
        align_object_to_axis(self._obj, self.axis)
        self._obj.location = midpoint(self.wc_start, self.wc_end)
        self._finalise()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """Return inlet (start) and outlet (end) positions."""
        return {
            "start": self.wc_start.copy(),
            "end":   self.wc_end.copy(),
        }
