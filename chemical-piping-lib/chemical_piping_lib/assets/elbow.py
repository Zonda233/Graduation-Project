"""
elbow.py
========
Bent-pipe (elbow) asset — the geometrically most complex component.

JSON component schema (excerpt)
--------------------------------
.. code-block:: json

    {
        "comp_id"       : "seg01_c02",
        "type"          : "Elbow",
        "wc_center"     : [0.7, 0.7, 0.6],
        "axis_in"       : "+Z",
        "axis_out"      : "+X",
        "angle_deg"     : 90,
        "bend_radius_m" : 0.15
    }

Geometry strategy
-----------------
A **pure bmesh arc-sweep** approach is used (no ``bpy.ops``):

1. Call :func:`coords.compute_elbow_arc` to obtain the sequence of
   ``(centre, tangent)`` pairs along the arc centre-line.
2. For each pair, generate a ring of vertices via
   :func:`bmesh_utils.make_circle_verts`.
3. Bridge adjacent rings with :func:`bmesh_utils.bridge_loops`.
4. Cap both open ends with n-gon faces.
5. Recalculate normals.

Because every cross-section is placed directly at its world-space coordinate,
no post-construction rotation or translation of the Object is required — the
geometry is born in the correct position.

Bend radius default
-------------------
If ``bend_radius_m`` is absent from the JSON, the industry-standard
``1.5 × nominal_pipe_diameter`` is used (long-radius elbow, ASME B16.9).
"""

from __future__ import annotations

import logging

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import RUNTIME, get_dn_spec
from chemical_piping_lib.utils.bmesh_utils import (
    bm_to_object,
    make_elbow_sweep,
    recalc_normals,
)
from chemical_piping_lib.utils.coords import compute_elbow_arc

from .base import PipingAsset

log = logging.getLogger(__name__)


class Elbow(PipingAsset):
    """
    A bent-pipe elbow component.

    Parameters
    ----------
    comp_data:
        Component dict.  Required keys: ``wc_center``, ``axis_in``,
        ``axis_out``.  Optional: ``angle_deg`` (default 90),
        ``bend_radius_m`` (default 1.5 × OD).
    spec:
        Parent segment spec dict.  Must contain ``nominal_diameter``.
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

        self.wc_center  = Vector(comp_data["wc_center"])
        self.axis_in:  str = comp_data["axis_in"]
        self.axis_out: str = comp_data["axis_out"]
        self.angle_deg: float = float(comp_data.get("angle_deg", 90))

        # Pipe geometry.
        nominal_d = float(spec["nominal_diameter"])
        dn_spec   = get_dn_spec(nominal_d)
        self.outer_radius: float = dn_spec["outer_diameter"] / 2.0

        # Bend radius: JSON value or 1.5 × OD (industry standard).
        default_bend_r = 1.5 * dn_spec["outer_diameter"]
        self.bend_radius: float = float(
            comp_data.get("bend_radius_m", default_bend_r)
        )

        # Computed during build(); exposed for port queries.
        self._arc: list[tuple[Vector, Vector]] = []

    # ------------------------------------------------------------------
    # PipingAsset interface
    # ------------------------------------------------------------------

    def build(self) -> bpy.types.Object:
        """
        Build the elbow arc-sweep geometry.

        Returns
        -------
        The elbow ``bpy.types.Object``.
        """
        log.debug(
            "Elbow.build: %s  %s→%s  R=%.3f m",
            self.comp_id, self.axis_in, self.axis_out, self.bend_radius,
        )

        # --- 1. Compute arc centre-line --------------------------------
        self._arc = compute_elbow_arc(
            corner_wc=self.wc_center,
            axis_in=self.axis_in,
            axis_out=self.axis_out,
            bend_radius=self.bend_radius,
            n_segments=RUNTIME.elbow_arc_segments,
        )

        # --- 1b. Extend arc slightly into adjacent pipes to avoid seam ----
        # Prepend/append one ring so elbow mesh overlaps pipe ends by ~3 mm.
        _OVERLAP = 0.003
        first_centre, first_tan = self._arc[0]
        last_centre, last_tan = self._arc[-1]
        extended = [
            (first_centre - _OVERLAP * first_tan, first_tan),  # into incoming pipe
        ] + list(self._arc) + [
            (last_centre + _OVERLAP * last_tan, last_tan),     # into outgoing pipe
        ]
        self._arc = extended

        # --- 2. Build swept geometry in bmesh -------------------------
        bm = bmesh.new()
        make_elbow_sweep(
            bm,
            arc=self._arc,
            radius=self.outer_radius,
            segments=RUNTIME.mesh_segments,
        )
        recalc_normals(bm)

        # --- 3. Write to Object (no rotation needed — arc is in world space)
        self._obj = bm_to_object(bm, name=self.comp_id, collection=self.collection)
        # Location stays at world origin because vertex positions are already
        # in world space.  (Blender interprets mesh vertex coords relative to
        # the object's origin; since we never move the object its origin IS
        # the world origin, and the vertices encode absolute positions.)
        # This is correct and intentional.

        # --- 4. Finalise ----------------------------------------------
        self._finalise()

        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """
        Return the inlet and outlet centres of the elbow arc.

        Returns
        -------
        ``{"inlet": Vector, "outlet": Vector}``
        """
        if not self._arc:
            raise RuntimeError(
                f"Elbow '{self.comp_id}': get_ports() called before build()."
            )
        inlet_centre,  _ = self._arc[0]
        outlet_centre, _ = self._arc[-1]
        return {
            "inlet":  inlet_centre.copy(),
            "outlet": outlet_centre.copy(),
        }
