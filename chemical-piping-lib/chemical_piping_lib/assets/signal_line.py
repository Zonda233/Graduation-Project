"""
signal_line.py
==============
Instrument signal line (small-bore straight tubing) asset.

JSON component schema (excerpt)
-------------------------------
.. code-block:: json

    {
        "comp_id"  : "seg_sig_ti101_c00",
        "type"     : "SignalLine",
        "wc_start" : [0.5, 2.5, 0.3],
        "wc_end"   : [0.3, 2.5, 0.3],
        "axis"     : "-X",
        "length_m" : 0.2
    }

Geometry strategy
-----------------
SignalLine is always generated as a compact solid cylinder (no hollow tube
and no flange auto-insertion), because impulse/signal lines are represented as
lightweight routing geometry rather than process pipe spools.
"""

from __future__ import annotations

import logging

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import RUNTIME, resolve_pipe_cross_section
from chemical_piping_lib.utils.bmesh_utils import (
    bm_to_object,
    make_cylinder,
    recalc_normals,
)
from chemical_piping_lib.utils.coords import (
    align_object_to_axis,
    midpoint,
)

from .base import PipingAsset

log = logging.getLogger(__name__)


class SignalLine(PipingAsset):
    """
    A straight small-bore signal line segment.

    Parameters
    ----------
    comp_data:
        Component dict from ``segments[].components[]``.
        Must contain ``wc_start``, ``wc_end``, ``axis``, ``length_m``.
    spec:
        Parent segment ``spec`` dict.  Uses ``nominal_diameter``.
    material_id:
        Material key.
    collection:
        Optional target Blender collection.
    """

    def __init__(
        self,
        comp_data: dict,
        spec: dict,
        material_id: str,
        collection=None,
    ) -> None:
        super().__init__(comp_data, spec, material_id, collection)

        self.wc_start = Vector(comp_data["wc_start"])
        self.wc_end = Vector(comp_data["wc_end"])
        self.axis: str = comp_data["axis"]
        self.length_m = float(comp_data["length_m"])

        nominal_d = float(spec["nominal_diameter"])
        section = resolve_pipe_cross_section(nominal_d)
        self.outer_radius: float = section["outer_diameter"] / 2.0

    def build(self) -> bpy.types.Object:
        """
        Construct the signal line cylinder.

        Returns
        -------
        The signal line ``bpy.types.Object``.
        """
        log.debug(
            "SignalLine.build: %s  axis=%s  length=%.3f m",
            self.comp_id,
            self.axis,
            self.length_m,
        )

        bm = bmesh.new()
        make_cylinder(
            bm,
            radius=self.outer_radius,
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
        """
        Return the two end-points of the signal line.

        Returns
        -------
        ``{"start": Vector, "end": Vector}``
        """
        return {
            "start": self.wc_start.copy(),
            "end": self.wc_end.copy(),
        }

