"""
instrument.py
=============
Inline instrument asset (thermometer / pressure gauge).

JSON asset schema (excerpt)
---------------------------
.. code-block:: json

    {
        "id": "inst_TI101",
        "type": "Instrument",
        "instrument_kind": "thermometer",
        "wc_center": [0.5, 2.5, 0.3],
        "material_id": "mat_carbon_steel",
        "geometry": {
            "face_axis": "+X"
        },
        "ports": [
            {
                "port_id": "inst_TI101",
                "wc": [0.5, 2.5, 0.3],
                "direction": "+X",
                "nominal_diameter": 0.006
            }
        ]
    }

Geometry strategy
-----------------
* **thermometer**: slender stem cylinder with a small bulb.
* **pressure_gauge**: short socket plus dial body.

The object is created along local +Z and then aligned to ``face_axis``.
Port coordinates are taken from JSON ``ports[].wc`` when provided so segment
endpoints can align exactly with routing output.
"""

from __future__ import annotations

import logging

import bmesh
import bpy
from mathutils import Matrix, Vector

from chemical_piping_lib.config import RUNTIME
from chemical_piping_lib.utils.bmesh_utils import bm_to_object, make_cylinder, recalc_normals
from chemical_piping_lib.utils.coords import align_object_to_axis, axis_to_vec

from .base import PipingAsset

log = logging.getLogger(__name__)


class Instrument(PipingAsset):
    """
    Inline instrument asset used by signal line segments.

    Parameters
    ----------
    comp_data:
        Asset dict from ``json_data["assets"]`` with ``type == "Instrument"``.
    spec:
        Unused for Instrument; pass an empty dict.
    material_id:
        Material key.
    collection:
        Optional target collection.
    """

    def __init__(
        self,
        comp_data: dict,
        spec: dict,
        material_id: str,
        collection=None,
    ) -> None:
        super().__init__(comp_data, spec, material_id, collection)

        self.instrument_kind: str = str(comp_data.get("instrument_kind", "pressure_gauge"))
        self.wc_center = Vector(comp_data["wc_center"])
        self.geometry = comp_data.get("geometry", {}) or {}
        self.face_axis: str = str(self.geometry.get("face_axis", "+X"))
        self.ports_def: list[dict] = list(comp_data.get("ports", []))
        self._port_positions: dict[str, Vector] = {}

    def build(self) -> bpy.types.Object:
        """
        Construct the instrument mesh and register its world-space ports.

        Returns
        -------
        The instrument ``bpy.types.Object``.
        """
        log.debug(
            "Instrument.build: %s  kind=%s  face_axis=%s",
            self.comp_id,
            self.instrument_kind,
            self.face_axis,
        )

        if self.instrument_kind == "thermometer":
            bm = self._build_thermometer_bmesh()
        else:
            bm = self._build_pressure_gauge_bmesh()

        self._obj = bm_to_object(bm, name=self.comp_id, collection=self.collection)
        align_object_to_axis(self._obj, self.face_axis)
        self._obj.location = self.wc_center
        self._finalise()

        self._cache_port_positions()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """
        Return instrument port coordinates keyed by ``port_id``.
        """
        return {pid: wc.copy() for pid, wc in self._port_positions.items()}

    def _build_thermometer_bmesh(self) -> bmesh.types.BMesh:
        bm = bmesh.new()
        stem_length = float(self.geometry.get("stem_length_m", 0.18))
        stem_radius = float(self.geometry.get("stem_radius_m", 0.006))
        bulb_radius = float(self.geometry.get("bulb_radius_m", 0.014))

        make_cylinder(
            bm,
            radius=stem_radius,
            depth=stem_length,
            segments=max(12, RUNTIME.mesh_segments // 2),
            center=Vector((0.0, 0.0, stem_length / 2.0)),
        )
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=max(12, RUNTIME.mesh_segments // 2),
            v_segments=max(6, RUNTIME.mesh_segments // 4),
            radius=bulb_radius,
            matrix=Matrix.Translation(Vector((0.0, 0.0, -bulb_radius))),
        )
        recalc_normals(bm)
        return bm

    def _build_pressure_gauge_bmesh(self) -> bmesh.types.BMesh:
        bm = bmesh.new()
        dial_radius = float(self.geometry.get("dial_radius_m", 0.035))
        dial_depth = float(self.geometry.get("dial_depth_m", 0.016))
        socket_radius = float(self.geometry.get("socket_radius_m", 0.007))
        socket_len = float(self.geometry.get("socket_length_m", 0.03))

        make_cylinder(
            bm,
            radius=dial_radius,
            depth=dial_depth,
            segments=RUNTIME.mesh_segments,
            center=Vector((0.0, 0.0, dial_depth / 2.0)),
        )
        make_cylinder(
            bm,
            radius=socket_radius,
            depth=socket_len,
            segments=max(12, RUNTIME.mesh_segments // 2),
            center=Vector((0.0, 0.0, -socket_len / 2.0)),
        )
        recalc_normals(bm)
        return bm

    def _cache_port_positions(self) -> None:
        if self.ports_def:
            for port in self.ports_def:
                port_id = str(port.get("port_id", "")).strip()
                if not port_id:
                    continue
                if "wc" in port:
                    self._port_positions[port_id] = Vector(port["wc"])
                else:
                    direction = str(port.get("direction", self.face_axis))
                    vec = axis_to_vec(direction)
                    self._port_positions[port_id] = self.wc_center + vec * 0.02
            return

        # Fallback: expose at least one deterministic port.
        self._port_positions[self.comp_id] = self.wc_center.copy()

