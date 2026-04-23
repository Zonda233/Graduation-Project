from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

from ..assets.geometry_helper import GeometryHelper
from ..config import RouterConfig
from ..grid.voxel_geometry import VoxelGeometryMaps
from ..models.domain_types import PlacedNodeMap
from ..models.input_models import NodeSpec, RouterInput


@dataclass
class EquipmentPortShellSnapper:
    """Snap placeholder tank signal ports onto the cylindrical shell before routing."""

    def apply(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        config: RouterConfig,
    ) -> None:
        geometry = GeometryHelper(config)
        existing_equipment = {n.node_id for n in router_input.nodes if n.node_type == "Equipment"}

        grouped_ports: Dict[str, List[NodeSpec]] = {}
        for node in router_input.nodes:
            if node.node_type != "EquipmentPort" or not node.equipment_ref:
                continue
            if node.equipment_ref in existing_equipment:
                continue
            if node.node_id not in placed_nodes:
                continue
            grouped_ports.setdefault(node.equipment_ref, []).append(node)

        for ports in grouped_ports.values():
            if not ports:
                continue
            center_wc = self._resolve_tank_center_wc(ports, placed_nodes, geometry)
            for node in ports:
                if not self._is_signal_port(node):
                    continue
                placed = placed_nodes[node.node_id]
                snapped_wc = self._snap_to_shell(
                    wc=placed.wc,
                    center_wc=center_wc,
                    shell_radius=geometry.SHELL_RADIUS,
                    shell_height=geometry.SHELL_HEIGHT,
                )
                snapped_vc = geometry.world_to_voxel(list(snapped_wc))
                snapped_wc_exact = VoxelGeometryMaps.vc_to_wc(snapped_vc, config)
                placed.wc = (
                    float(snapped_wc_exact[0]),
                    float(snapped_wc_exact[1]),
                    float(snapped_wc_exact[2]),
                )
                placed.vc = snapped_vc

    def _resolve_tank_center_wc(
        self,
        ports: List[NodeSpec],
        placed_nodes: PlacedNodeMap,
        geometry: GeometryHelper,
    ) -> tuple[float, float, float]:
        base_node = next((p for p in ports if not self._is_signal_port(p)), ports[0])
        base_wc = list(placed_nodes[base_node.node_id].wc)
        wc_center = geometry.compute_tank_wc_center(base_wc)
        return (float(wc_center[0]), float(wc_center[1]), float(wc_center[2]))

    @staticmethod
    def _is_signal_port(node: NodeSpec) -> bool:
        role = (node.role or "").strip().lower()
        if role == "signal":
            return True
        port_kind = str(node.properties.get("port_kind", "")).strip().lower()
        if port_kind == "instrument_tap":
            return True
        return bool(node.properties.get("snap_to_shell"))

    @staticmethod
    def _snap_to_shell(
        wc: tuple[float, float, float],
        center_wc: tuple[float, float, float],
        shell_radius: float,
        shell_height: float,
    ) -> tuple[float, float, float]:
        dx = float(wc[0] - center_wc[0])
        dy = float(wc[1] - center_wc[1])
        radial_len = math.hypot(dx, dy)
        if radial_len < 1e-9:
            dx, dy = 1.0, 0.0
            radial_len = 1.0
        sx = center_wc[0] + shell_radius * dx / radial_len
        sy = center_wc[1] + shell_radius * dy / radial_len
        half_h = shell_height / 2.0
        z_min = center_wc[2] - half_h
        z_max = center_wc[2] + half_h
        sz = min(max(float(wc[2]), z_min), z_max)
        return (sx, sy, sz)
