"""
custom_module.py
================
Custom/unknown module asset represented as a box that fills voxel_extent.

JSON asset schema (excerpt)
---------------------------
.. code-block:: json

    {
        "id": "custom_module_01",
        "type": "CustomModule",
        "wc_center": [2.5, 3.1, 0.3],
        "voxel_extent": [3, 2, 2],
        "material_id": "mat_carbon_steel",
        "geometry": {
            "shape": "box"
        },
        "ports": [
            {
                "port_id": "port_custom_module_01_in",
                "direction": "-X",
                "port_kind": "process",
                "local_wc": [-0.3, 0.0, 0.0],
                "wc": [2.2, 3.1, 0.3],
                "vc": [10, 15, 1],
                "nominal_diameter": 0.08
            }
        ]
    }

Geometry strategy
-----------------
The module body is generated as a cuboid whose edge lengths match
``voxel_extent * voxel_size`` by default.  Port positions are read from
``ports[].wc`` first, then from ``ports[].local_wc`` offset from module
centre if world coordinates are not explicitly provided.
"""

from __future__ import annotations

import logging

import bmesh
import bpy
from mathutils import Vector

from chemical_piping_lib.config import RUNTIME
from chemical_piping_lib.utils.bmesh_utils import bm_to_object, recalc_normals

from .base import PipingAsset

log = logging.getLogger(__name__)


class CustomModule(PipingAsset):
    """
    Box-shaped placeholder module with arbitrary port definitions.

    Parameters
    ----------
    comp_data:
        Asset dict from ``json_data["assets"]`` where ``type == "CustomModule"``.
    spec:
        Unused for CustomModule; pass an empty dict.
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
        self.wc_center = Vector(comp_data["wc_center"])
        self.voxel_extent = tuple(int(v) for v in comp_data.get("voxel_extent", [1, 1, 1]))
        self.geometry = comp_data.get("geometry", {}) or {}
        self.ports_def: list[dict] = list(comp_data.get("ports", []))
        self._port_positions: dict[str, Vector] = {}

        size_xyz = self.geometry.get("size_xyz_m")
        if isinstance(size_xyz, list) and len(size_xyz) == 3:
            self.size_x = float(size_xyz[0])
            self.size_y = float(size_xyz[1])
            self.size_z = float(size_xyz[2])
        else:
            vs = float(RUNTIME.voxel_size)
            ex, ey, ez = self.voxel_extent
            self.size_x = max(vs * ex, 1e-6)
            self.size_y = max(vs * ey, 1e-6)
            self.size_z = max(vs * ez, 1e-6)

    def build(self) -> bpy.types.Object:
        """
        Build the module cuboid and cache port world coordinates.

        Returns
        -------
        The module ``bpy.types.Object``.
        """
        log.debug(
            "CustomModule.build: %s  size=(%.3f, %.3f, %.3f)",
            self.comp_id,
            self.size_x,
            self.size_y,
            self.size_z,
        )

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)

        # Unit cube half-size is 1.0, so scale to half target dimensions.
        scale_vec = Vector((self.size_x / 2.0, self.size_y / 2.0, self.size_z / 2.0))
        bmesh.ops.scale(bm, verts=bm.verts, vec=scale_vec)
        recalc_normals(bm)

        self._obj = bm_to_object(bm, name=self.comp_id, collection=self.collection)
        self._obj.location = self.wc_center
        self._finalise()
        self._cache_ports()
        return self._obj

    def get_ports(self) -> dict[str, Vector]:
        """
        Return module ports keyed by ``port_id``.
        """
        return {pid: wc.copy() for pid, wc in self._port_positions.items()}

    def _cache_ports(self) -> None:
        for port in self.ports_def:
            port_id = str(port.get("port_id", "")).strip()
            if not port_id:
                continue
            if "wc" in port:
                self._port_positions[port_id] = Vector(port["wc"])
                continue
            if "local_wc" in port:
                self._port_positions[port_id] = self.wc_center + Vector(port["local_wc"])
                continue
            self._port_positions[port_id] = self.wc_center.copy()

