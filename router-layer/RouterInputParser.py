from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union

from .RouterInputModels import (
    BBoxHint,
    ConstraintsSpec,
    LineSpec,
    NodeSpec,
    PlacementHint,
    RouterInput,
    SpatialRules,
)


@dataclass
class RouterInputParser:
    """Parses raw router-input JSON dict into strongly typed dataclasses."""

    # 默认值常量
    DEFAULT_CLEARANCE_VOXELS = 0
    DEFAULT_MAX_SEARCH_RADIUS_VOXELS = 4
    DEFAULT_Z_LAYERS = [0]

    # ---------- 安全取值辅助函数 ----------
    @staticmethod
    def _safe_get_str(raw: Dict[str, Any], key: str, default: str = "") -> str:
        val = raw.get(key)
        return str(val) if val is not None else default

    @staticmethod
    def _safe_get_float(raw: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
        val = raw.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_get_int(raw: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
        val = raw.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_get_bool(raw: Dict[str, Any], key: str, default: bool = False) -> bool:
        val = raw.get(key)
        if val is None:
            return default
        return bool(val)

    @staticmethod
    def _safe_get_dict(raw: Dict[str, Any], key: str) -> Dict[str, Any]:
        val = raw.get(key)
        return val if isinstance(val, dict) else {}

    @staticmethod
    def _safe_get_list(raw: Dict[str, Any], key: str) -> List[Any]:
        val = raw.get(key)
        return val if isinstance(val, list) else []

    @staticmethod
    def _safe_get_int_list(raw: Dict[str, Any], key: str) -> List[int]:
        lst = RouterInputParser._safe_get_list(raw, key)
        return [int(v) for v in lst if isinstance(v, int)]

    @staticmethod
    def _safe_get_str_list(raw: Dict[str, Any], key: str) -> List[str]:
        lst = RouterInputParser._safe_get_list(raw, key)
        return [str(v) for v in lst if isinstance(v, str)]

    # ---------- 公共入口 ----------
    def parse(self, raw: Dict[str, object]) -> RouterInput:
        nodes_raw = self._safe_get_list(raw, "nodes")
        lines_raw = self._safe_get_list(raw, "lines")
        constraints_raw = self._safe_get_dict(raw, "constraints")
        meta = raw.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        constraints = self._parse_constraints(constraints_raw)
        nodes = [self._parse_node(n) for n in nodes_raw if isinstance(n, dict)]
        lines = [self._parse_line(l) for l in lines_raw if isinstance(l, dict)]

        return RouterInput(
            meta=meta,
            nodes=nodes,
            lines=lines,
            constraints=constraints,
            raw=raw,
        )

    # ---------- 约束解析 ----------
    def _parse_constraints(self, raw: Dict[str, Any]) -> ConstraintsSpec:
        spatial_raw = self._safe_get_dict(raw, "spatial_rules")
        default_layers = self._safe_get_int_list(spatial_raw, "default_z_layers")
        if not default_layers:
            default_layers = self.DEFAULT_Z_LAYERS

        spatial = SpatialRules(
            default_clearance_voxels=self._safe_get_int(spatial_raw, "default_clearance_voxels", self.DEFAULT_CLEARANCE_VOXELS),
            max_search_radius_voxels=self._safe_get_int(spatial_raw, "max_search_radius_voxels", self.DEFAULT_MAX_SEARCH_RADIUS_VOXELS),
            default_z_layers=default_layers,
        )
        return ConstraintsSpec(spatial_rules=spatial)

    # ---------- 节点解析 ----------
    def _parse_node(self, raw: Dict[str, Any]) -> NodeSpec:
        loc_raw = self._safe_get_dict(raw, "location_2d")
        placement_raw = self._safe_get_dict(raw, "placement_hint")
        bbox_raw = self._safe_get_dict(raw, "bbox_hint")

        location_2d_x = self._safe_get_float(loc_raw, "x")
        location_2d_y = self._safe_get_float(loc_raw, "y")
        placement_hint = self._parse_placement_hint(placement_raw)
        bbox_hint = self._parse_bbox_hint(bbox_raw)

        return NodeSpec(
            node_id=self._safe_get_str(raw, "id"),
            node_type=self._safe_get_str(raw, "type"),
            role=self._safe_get_str(raw, "role", default=None),
            label=self._safe_get_str(raw, "label", default=None),
            pid_tag=self._safe_get_str(raw, "pid_tag", default=None),
            equipment_ref=self._safe_get_str(raw, "equipment_ref", default=None),
            location_2d_x=location_2d_x,
            location_2d_y=location_2d_y,
            placement_hint=placement_hint,
            bbox_hint=bbox_hint,
        )

    def _parse_placement_hint(self, raw: Dict[str, Any]) -> PlacementHint:
        z_layers = self._safe_get_int_list(raw, "z_layers")
        return PlacementHint(
            z_layers=z_layers,
            anchor_policy=self._safe_get_str(raw, "anchor_policy", default=None),
            direction_preferred=self._safe_get_str(raw, "direction_preferred", default=None),
        )

    def _parse_bbox_hint(self, raw: Dict[str, Any]) -> BBoxHint:
        extent = self._safe_get_int_list(raw, "extent_voxels")
        clearance = self._safe_get_int(raw, "clearance_voxels")
        return BBoxHint(
            extent_voxels=extent,
            clearance_voxels=clearance,
        )

    # ---------- 连线解析 ----------
    def _parse_line(self, raw: Dict[str, Any]) -> LineSpec:
        via = self._safe_get_str_list(raw, "via_nodes")
        return LineSpec(
            line_id=self._safe_get_str(raw, "id"),
            tag=self._safe_get_str(raw, "tag", default=None),
            from_node_id=self._safe_get_str(raw, "from_node"),
            to_node_id=self._safe_get_str(raw, "to_node"),
            via_node_ids=via,
            nominal_diameter_mm=self._safe_get_float(raw, "nominal_diameter_mm", default=None),
            with_flanges=self._safe_get_bool(raw, "with_flanges", default=False),
            raw=raw,
        )