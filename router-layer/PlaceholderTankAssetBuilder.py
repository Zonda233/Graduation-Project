from __future__ import annotations

import math
from typing import Dict, List, Set
from dataclasses import dataclass

from .RouterInputModels import NodeSpec, RouterInput
from .config import RouterConfig
from .domain_types import PlacedNode, PlacedNodeMap


@dataclass
class EquipmentPortInfo:
    """携带端口相关信息的简单数据类"""
    port_id: str
    placed_node: PlacedNode
    node_spec: NodeSpec


class GeometryHelper:
    """处理世界坐标与体素坐标转换、罐体几何计算"""
    # 罐体几何参数
    SHELL_RADIUS = 0.3
    SHELL_HEIGHT = 0.5
    HEAD_RATIO = 0.25
    HEAD_HEIGHT = SHELL_RADIUS * HEAD_RATIO
    VOXEL_ORIGIN_OFFSET = [-2, -2, -3]   # 相对于中心体素的偏移
    VOXEL_EXTENT = [4, 4, 6]

    def __init__(self, config: RouterConfig):
        self.origin_wc = config.origin_wc
        self.voxel_size = config.voxel_size

    def world_to_voxel(self, wc: list[float]) -> tuple[int, int, int]:
        """将世界坐标转换为体素坐标（基于原点和体素大小）"""
        ox, oy, oz = self.origin_wc
        vs = self.voxel_size
        vx = int(round((wc[0] - ox) / vs - 0.5))
        vy = int(round((wc[1] - oy) / vs - 0.5))
        vz = int(round((wc[2] - oz) / vs - 0.5))
        return vx, vy, vz

    def compute_tank_wc_center(self, base_wc: list[float]) -> list[float]:
        """根据端口位置计算罐体世界坐标中心"""
        return [
            base_wc[0],
            base_wc[1],
            base_wc[2] + self.SHELL_HEIGHT / 2.0 + self.HEAD_HEIGHT,
        ]

    def compute_voxel_origin_and_extent(
        self, center_voxel: tuple[int, int, int]
    ) -> tuple[list[int], list[int]]:
        """根据体素中心计算罐体的体素原点和范围"""
        cx, cy, cz = center_voxel
        origin = [
            cx + self.VOXEL_ORIGIN_OFFSET[0],
            cy + self.VOXEL_ORIGIN_OFFSET[1],
            max(0, cz + self.VOXEL_ORIGIN_OFFSET[2]),
        ]
        extent = self.VOXEL_EXTENT.copy()
        return origin, extent


class PlaceholderTankAssetBuilder:
    """Builds placeholder Tank assets for equipment_ref without an explicit Equipment node."""

    def build(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        config: RouterConfig,
    ) -> List[Dict[str, object]]:
        # 初始化几何辅助类
        geometry = GeometryHelper(config)

        # 1. 收集所有 EquipmentPort 并按 equipment_ref 分组
        ports_by_equipment = self._collect_ports_by_equipment(router_input, placed_nodes)

        # 2. 获取已存在的 Equipment 节点 ID
        existing_equipment = {n.node_id for n in router_input.nodes if n.node_type == "Equipment"}

        # 3. 为每个需要创建设备的 equipment_ref 构建资产
        assets = []
        for eid, port_infos in ports_by_equipment.items():
            if eid in existing_equipment:
                continue
            asset = self._build_asset(eid, port_infos, geometry)
            if asset:
                assets.append(asset)

        return assets

    def _collect_ports_by_equipment(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
    ) -> Dict[str, List[EquipmentPortInfo]]:
        """收集所有 EquipmentPort，按 equipment_ref 分组"""
        result: Dict[str, List[EquipmentPortInfo]] = {}
        for node in router_input.nodes:
            if node.node_type != "EquipmentPort" or not node.equipment_ref:
                continue
            placed = placed_nodes.get(node.node_id)
            if not placed:
                continue
            eid = node.equipment_ref
            result.setdefault(eid, []).append(
                EquipmentPortInfo(node.node_id, placed, node)
            )
        return result

    def _build_asset(
        self,
        equipment_id: str,
        port_infos: List[EquipmentPortInfo],
        geometry: GeometryHelper,
    ) -> Dict[str, object] | None:
        """为单个 equipment_ref 构建资产字典"""
        if not port_infos:
            return None

        # 以第一个端口的位置为基准
        first_port = port_infos[0]
        base_wc = first_port.placed_node.wc

        # 计算罐体几何
        wc_center = geometry.compute_tank_wc_center(base_wc)
        center_voxel = geometry.world_to_voxel(wc_center)
        voxel_origin, voxel_extent = geometry.compute_voxel_origin_and_extent(center_voxel)

        # 构建端口 JSON
        ports_json = [self._build_port_json(p, wc_center) for p in port_infos]

        # 构建几何字典
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

    @staticmethod
    def _build_port_json(
        port_info: EquipmentPortInfo,
        tank_wc_center: list[float],
    ) -> Dict[str, object]:
        """将单个端口信息转换为 JSON 格式"""
        role = (port_info.node_spec.role or "outlet")
        is_signal = PlaceholderTankAssetBuilder._is_signal_port(port_info.node_spec)
        nominal_diameter = PlaceholderTankAssetBuilder._resolve_nominal_diameter_m(
            port_info.node_spec,
            is_signal,
        )
        direction = PlaceholderTankAssetBuilder._resolve_port_direction(
            port_wc=port_info.placed_node.wc,
            tank_wc_center=tank_wc_center,
            is_signal=is_signal,
        )
        port_json = {
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
            mm = float(raw)
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