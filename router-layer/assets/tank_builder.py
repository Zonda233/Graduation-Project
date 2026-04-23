from __future__ import annotations

import math
from typing import Dict, List

from ..config import RouterConfig
from ..models.domain_types import PlacedNodeMap
from ..models.input_models import NodeSpec, RouterInput
from .geometry_helper import EquipmentPortInfo, GeometryHelper


class PlaceholderTankAssetBuilder:
    """Builds placeholder Tank assets for equipment_ref without an explicit Equipment node."""

    def build(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        config: RouterConfig,
    ) -> List[Dict[str, object]]:
        geometry = GeometryHelper(config)
        ports_by_equipment = self._collect_ports_by_equipment(router_input, placed_nodes)
        existing_equipment = {n.node_id for n in router_input.nodes if n.node_type == "Equipment"}

        assets = []
        for eid, port_infos in ports_by_equipment.items():
            if eid in existing_equipment:
                continue
            if self._is_custom_module_group(port_infos):
                asset = self._build_custom_module_asset(eid, port_infos, geometry)
            else:
                asset = self._build_asset(eid, port_infos, geometry)
            if asset:
                assets.append(asset)
        return assets

    def _collect_ports_by_equipment(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
    ) -> Dict[str, List[EquipmentPortInfo]]:
        result: Dict[str, List[EquipmentPortInfo]] = {}
        for node in router_input.nodes:
            if node.node_type != "EquipmentPort" or not node.equipment_ref:
                continue
            placed = placed_nodes.get(node.node_id)
            if not placed:
                continue
            eid = node.equipment_ref
            result.setdefault(eid, []).append(EquipmentPortInfo(node.node_id, placed, node))
        return result

    def _build_asset(
        self,
        equipment_id: str,
        port_infos: List[EquipmentPortInfo],
        geometry: GeometryHelper,
    ) -> Dict[str, object] | None:
        if not port_infos:
            return None
        first_port = port_infos[0]
        base_wc = first_port.placed_node.wc
        wc_center = geometry.compute_tank_wc_center(base_wc)
        center_voxel = geometry.world_to_voxel(wc_center)
        voxel_origin, voxel_extent = geometry.compute_voxel_origin_and_extent(center_voxel)
        ports_json = [self._build_port_json(p, wc_center) for p in port_infos]
        geometry_dict = {
            "shell_radius": geometry.SHELL_RADIUS,
            "shell_height": geometry.SHELL_HEIGHT,
            "head_type": "ellipsoidal",
            "head_ratio": geometry.HEAD_RATIO,
            "orientation": "vertical",
        }
        return {
            "id": equipment_id,
            "type": "Tank",
            "display_name": f"Placeholder {equipment_id}",
            "voxel_origin": voxel_origin,
            "voxel_extent": voxel_extent,
            "wc_center": [round(v, 6) for v in wc_center],
            "material_id": "mat_carbon_steel",
            "geometry": geometry_dict,
            "ports": ports_json,
        }

    def _build_custom_module_asset(
        self,
        equipment_id: str,
        port_infos: List[EquipmentPortInfo],
        geometry: GeometryHelper,
    ) -> Dict[str, object] | None:
        if not port_infos:
            return None
        wc_center = self._resolve_custom_module_center(port_infos)
        center_vc = geometry.world_to_voxel([wc_center[0], wc_center[1], wc_center[2]])
        center_vc_wc = [
            round(geometry.origin_wc[i] + (center_vc[i] + 0.5) * geometry.voxel_size, 6)
            for i in range(3)
        ]
        module_wc_center = (center_vc_wc[0], center_vc_wc[1], center_vc_wc[2])
        voxel_extent = self._resolve_custom_module_extent(port_infos)
        voxel_origin = [
            center_vc[0] - voxel_extent[0] // 2,
            center_vc[1] - voxel_extent[1] // 2,
            max(0, center_vc[2] - voxel_extent[2] // 2),
        ]
        ports_json = [
            self._build_custom_module_port_json(port_info, module_wc_center, geometry)
            for port_info in port_infos
        ]
        size_xyz_m = [round(v * geometry.voxel_size, 6) for v in voxel_extent]
        return {
            "id": equipment_id,
            "type": "CustomModule",
            "display_name": f"Custom {equipment_id}",
            "voxel_origin": voxel_origin,
            "voxel_extent": voxel_extent,
            "wc_center": [round(v, 6) for v in module_wc_center],
            "material_id": "mat_carbon_steel",
            "geometry": {
                "shape": "box",
                "size_xyz_m": size_xyz_m,
                "category": "custom_unknown",
            },
            "ports": ports_json,
        }

    @staticmethod
    def _is_custom_module_group(port_infos: List[EquipmentPortInfo]) -> bool:
        for port_info in port_infos:
            asset_type = str(port_info.node_spec.properties.get("asset_type", "")).strip().lower()
            module_kind = str(port_info.node_spec.properties.get("module_kind", "")).strip().lower()
            if asset_type == "custom_module" or module_kind == "custom":
                return True
        return False

    @staticmethod
    def _resolve_custom_module_center(
        port_infos: List[EquipmentPortInfo],
    ) -> tuple[float, float, float]:
        inferred: List[tuple[float, float, float]] = []
        for port_info in port_infos:
            local_wc = port_info.node_spec.properties.get("port_local_wc")
            if not (isinstance(local_wc, list) and len(local_wc) == 3):
                continue
            px, py, pz = port_info.placed_node.wc
            inferred.append((
                float(px - float(local_wc[0])),
                float(py - float(local_wc[1])),
                float(pz - float(local_wc[2])),
            ))
        if inferred:
            n = float(len(inferred))
            return (
                sum(c[0] for c in inferred) / n,
                sum(c[1] for c in inferred) / n,
                sum(c[2] for c in inferred) / n,
            )
        n = float(len(port_infos))
        return (
            sum(p.placed_node.wc[0] for p in port_infos) / n,
            sum(p.placed_node.wc[1] for p in port_infos) / n,
            sum(p.placed_node.wc[2] for p in port_infos) / n,
        )

    @staticmethod
    def _resolve_custom_module_extent(port_infos: List[EquipmentPortInfo]) -> list[int]:
        for port_info in port_infos:
            raw = port_info.node_spec.properties.get("module_voxel_extent")
            if isinstance(raw, list) and len(raw) == 3:
                return [max(1, int(raw[0])), max(1, int(raw[1])), max(1, int(raw[2]))]
        return [3, 2, 2]

    @staticmethod
    def _build_custom_module_port_json(
        port_info: EquipmentPortInfo,
        module_center_wc: tuple[float, float, float],
        geometry: GeometryHelper,
    ) -> Dict[str, object]:
        props = port_info.node_spec.properties
        wc = [
            float(port_info.placed_node.wc[0]),
            float(port_info.placed_node.wc[1]),
            float(port_info.placed_node.wc[2]),
        ]
        local_wc = [
            wc[0] - module_center_wc[0],
            wc[1] - module_center_wc[1],
            wc[2] - module_center_wc[2],
        ]
        vc = list(geometry.world_to_voxel(wc))
        direction = (
            port_info.node_spec.placement_hint.direction_preferred
            or PlaceholderTankAssetBuilder._infer_direction_from_local(local_wc)
        )
        nominal_d = PlaceholderTankAssetBuilder._resolve_nominal_diameter_m(
            port_info.node_spec,
            is_signal=(str(props.get("port_kind", "")).strip().lower() == "signal"),
        )
        port_kind = str(props.get("port_kind", port_info.node_spec.role or "process"))
        return {
            "port_id": port_info.port_id,
            "role": port_info.node_spec.role or "outlet",
            "port_kind": port_kind,
            "local_wc": [round(v, 6) for v in local_wc],
            "vc": vc,
            "wc": [round(v, 6) for v in wc],
            "direction": direction,
            "nominal_diameter": nominal_d,
        }

    @staticmethod
    def _infer_direction_from_local(local_wc: list[float]) -> str:
        dx, dy, dz = float(local_wc[0]), float(local_wc[1]), float(local_wc[2])
        ax, ay, az = abs(dx), abs(dy), abs(dz)
        if ax >= ay and ax >= az:
            return "+X" if dx >= 0.0 else "-X"
        if ay >= ax and ay >= az:
            return "+Y" if dy >= 0.0 else "-Y"
        return "+Z" if dz >= 0.0 else "-Z"

    @staticmethod
    def _build_port_json(
        port_info: EquipmentPortInfo,
        tank_wc_center: list[float],
    ) -> Dict[str, object]:
        role = port_info.node_spec.role or "outlet"
        is_signal = PlaceholderTankAssetBuilder._is_signal_port(port_info.node_spec)
        nominal_diameter = PlaceholderTankAssetBuilder._resolve_nominal_diameter_m(
            port_info.node_spec, is_signal
        )
        direction = PlaceholderTankAssetBuilder._resolve_port_direction(
            port_wc=port_info.placed_node.wc,
            tank_wc_center=tank_wc_center,
            is_signal=is_signal,
        )
        port_json: Dict[str, object] = {
            "port_id": port_info.port_id,
            "role": role,
            "vc": list(port_info.placed_node.vc),
            "wc": list(port_info.placed_node.wc),
            "direction": direction,
            "nominal_diameter": nominal_diameter,
        }
        if is_signal:
            port_json["logical_port_only"] = True
        return port_json

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
    def _resolve_nominal_diameter_m(node: NodeSpec, is_signal: bool) -> float:
        raw = node.properties.get("nominal_diameter_mm")
        try:
            mm = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            mm = 6.0 if is_signal else 100.0
        if mm <= 0.0:
            mm = 6.0 if is_signal else 100.0
        return mm / 1000.0

    @staticmethod
    def _resolve_port_direction(
        port_wc: tuple[float, float, float],
        tank_wc_center: list[float],
        is_signal: bool,
    ) -> str:
        if not is_signal:
            return "-Z"
        dx = float(port_wc[0] - tank_wc_center[0])
        dy = float(port_wc[1] - tank_wc_center[1])
        if math.hypot(dx, dy) < 1e-9:
            return "+X"
        if abs(dx) >= abs(dy):
            return "+X" if dx >= 0.0 else "-X"
        return "+Y" if dy >= 0.0 else "-Y"
