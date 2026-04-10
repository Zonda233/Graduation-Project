"""
tee.py
======
Pipe tee (three-way junction) asset.

A Tee is a topological junction: it belongs to **two or three pipe segments**
simultaneously and is therefore not part of any single segment's
``components`` array.  Instead it appears in the top-level ``tee_joints``
array of the JSON.

JSON tee_joint schema
---------------------
.. code-block:: json

    {
        "tee_id"    : "tee_01",
        "wc_center" : [1.1, 0.7, 0.6],
        "ports": [
            {"port_id": "tee_01_run_a",  "axis": "-X", "connects_to_comp": "seg01_c03"},
            {"port_id": "tee_01_run_b",  "axis": "+X", "connects_to_comp": "seg02_c01"},
            {"port_id": "tee_01_branch", "axis": "+Y", "connects_to_comp": "seg03_c01"}
        ],
        "spec": {
            "main_diameter"   : 0.1,
            "branch_diameter" : 0.1,
            "material_id"     : "carbon_steel"
        }
    }

Geometry strategy
-----------------
Two-phase boolean union (MANIFOLD solver, with fallback):

1. Build a **main-run cylinder** (axis = run_a → run_b direction,
   length = 3 × main OD to give boolean solver plenty of overlap).
2. Build a **branch cylinder** (axis = branch direction,
   length = 2 × main OD, also over-sized).
3. Boolean UNION the branch into the main.
4. Trim both ends of the main run to the correct port positions using
   the half-length of the Tee body (= 1.5 × OD by default).
   (In the voxel model we accept slight over/under-run at the ends;
   the pipes that connect snap to the port world coordinates.)
5. Recalculate normals.

Port identification
-------------------
The code identifies *run* ports vs *branch* port automatically:
* Two ports whose axis strings are opposites of each other → the **run**.
* The remaining port → the **branch**.
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
from chemical_piping_lib.utils.boolean_utils import boolean_union
from chemical_piping_lib.utils.coords import axis_to_vec

from .base import PipingAsset

log = logging.getLogger(__name__)

_RUN_LENGTH_FACTOR    = 3.0   # main-run cylinder length = N × OD
_BRANCH_LENGTH_FACTOR = 2.5   # branch cylinder length   = N × OD


class Tee(PipingAsset):
    """
    A three-way pipe junction.

    Parameters
    ----------
    comp_data:
        The tee_joint dict from the JSON.  Must contain ``tee_id``,
        ``wc_center``, ``ports`` (list of 3 port dicts), ``spec``.
        For compatibility with the base class the ``"id"`` key is also
        accepted (set to ``tee_id`` value by :class:`~scene.assembler`).
    spec:
        Spec dict with ``main_diameter``, optionally ``branch_diameter``.
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

        self.wc_center = Vector(comp_data["wc_center"])
        self.ports_def: list[dict] = comp_data["ports"]   # 3 port dicts

        # Resolve diameters.
        main_d   = float(spec.get("main_diameter",   spec.get("nominal_diameter", 0.1)))
        branch_d = float(spec.get("branch_diameter", main_d))

        self.main_radius:   float = get_dn_spec(main_d)["outer_diameter"]   / 2.0
        self.branch_radius: float = get_dn_spec(branch_d)["outer_diameter"] / 2.0

        # Identify run vs branch.
        self.run_a_axis, self.run_b_axis, self.branch_axis = \
            self._identify_ports()

        # Computed port world positions (set during build).
        self._port_positions: dict[str, Vector] = {}

    # ------------------------------------------------------------------
    # PipingAsset interface
    # ------------------------------------------------------------------

    def build(self) -> bpy.types.Object:
        log.debug(
            "Tee.build: %s  center=%s  run=%s/%s  branch=%s",
            self.comp_id, self.wc_center,
            self.run_a_axis, self.run_b_axis, self.branch_axis,
        )

        main_od  = self.main_radius   * 2.0
        branch_od = self.branch_radius * 2.0

        run_dir    = axis_to_vec(self.run_b_axis)    # run_a → run_b
        branch_dir = axis_to_vec(self.branch_axis)

        # --- 1. Main run cylinder (centred at wc_center) --------------
        run_length = main_od * _RUN_LENGTH_FACTOR
        bm_run = bmesh.new()
        make_cylinder(
            bm_run,
            radius=self.main_radius,
            depth=run_length,
            segments=RUNTIME.mesh_segments,
        )
        recalc_normals(bm_run)
        run_obj = bm_to_object(
            bm_run,
            name=f"{self.comp_id}_run",
            collection=self.collection,
        )
        # Rotate run cylinder so its +Z aligns with run direction.
        from chemical_piping_lib.utils.coords import align_object_to_axis
        align_object_to_axis(run_obj, self.run_b_axis)
        run_obj.location = self.wc_center.copy()

        # --- 2. Branch cylinder (centred at wc_center) ----------------
        branch_length = main_od * _BRANCH_LENGTH_FACTOR
        bm_branch = bmesh.new()
        make_cylinder(
            bm_branch,
            radius=self.branch_radius,
            depth=branch_length,
            segments=RUNTIME.mesh_segments,
        )
        recalc_normals(bm_branch)
        branch_obj = bm_to_object(
            bm_branch,
            name=f"{self.comp_id}_branch",
            collection=self.collection,
        )
        align_object_to_axis(branch_obj, self.branch_axis)
        branch_obj.location = self.wc_center.copy()

        # --- 3. Boolean UNION -----------------------------------------
        success = boolean_union(run_obj, branch_obj, keep_cutter=False)
        if not success:
            log.warning(
                "Tee.build: boolean union failed for %r; result is approximate.",
                self.comp_id,
            )

        # --- 4. Rename and store --------------------------------------
        run_obj.name      = self.comp_id
        run_obj.data.name = self.comp_id
        self._obj         = run_obj

        # --- 5. Compute port world positions --------------------------
        half_run    = run_length    / 2.0
        half_branch = branch_length / 2.0

        run_a_dir = axis_to_vec(self.run_a_axis)
        run_b_dir = axis_to_vec(self.run_b_axis)
        br_dir    = axis_to_vec(self.branch_axis)

        self._port_positions = {
            self.run_a_axis: self.wc_center + run_a_dir * half_run,
            self.run_b_axis: self.wc_center + run_b_dir * half_run,
            self.branch_axis: self.wc_center + br_dir  * half_branch,
        }

        self._finalise()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        if not self._port_positions:
            raise RuntimeError(
                f"Tee '{self.comp_id}': get_ports() called before build()."
            )
        return {k: v.copy() for k, v in self._port_positions.items()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _identify_ports(
        self,
    ) -> tuple[str, str, str]:
        """
        From the three port dicts, identify the two *run* axes and the
        *branch* axis.

        Run ports are those whose axes are anti-parallel (opposite strings
        after normalisation).  The remaining port is the branch.

        Returns
        -------
        ``(run_a_axis, run_b_axis, branch_axis)``

        Raises
        ------
        ValueError
            If no anti-parallel pair can be found (malformed tee).
        """
        axes = [p["axis"] for p in self.ports_def]
        if len(axes) != 3:
            raise ValueError(
                f"Tee {self.comp_id!r}: expected exactly 3 ports, got {len(axes)}."
            )

        _opp = {"+X": "-X", "-X": "+X", "+Y": "-Y", "-Y": "+Y", "+Z": "-Z", "-Z": "+Z"}

        for i, ax in enumerate(axes):
            for j, ax2 in enumerate(axes):
                if i != j and _opp[ax] == ax2:
                    branch_idx = next(k for k in range(3) if k != i and k != j)
                    return ax, ax2, axes[branch_idx]

        raise ValueError(
            f"Tee {self.comp_id!r}: cannot find anti-parallel port pair in {axes}. "
            "A valid tee needs one pair of opposite run ports."
        )
