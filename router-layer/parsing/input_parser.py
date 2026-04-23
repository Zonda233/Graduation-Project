from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..models.input_models import (
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

    DEFAULT_CLEARANCE_VOXELS = 0
    DEFAULT_MAX_SEARCH_RADIUS_VOXELS = 4
    DEFAULT_Z_LAYERS = [0]

    # ---------- safe accessors ----------

    @staticmethod
    def _safe_str(raw: Dict[str, Any], key: str, default: Optional[str] = None) -> Optional[str]:
        val = raw.get(key)
        return str(val) if val is not None else default

    @staticmethod
    def _safe_float(raw: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
        val = raw.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(raw: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
        val = raw.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_bool(raw: Dict[str, Any], key: str, default: bool = False) -> bool:
        val = raw.get(key)
        return bool(val) if val is not None else default

    @staticmethod
    def _safe_dict(raw: Dict[str, Any], key: str) -> Dict[str, Any]:
        val = raw.get(key)
        return val if isinstance(val, dict) else {}

    @staticmethod
    def _safe_list(raw: Dict[str, Any], key: str) -> List[Any]:
        val = raw.get(key)
        return val if isinstance(val, list) else []

    @staticmethod
    def _safe_int_list(raw: Dict[str, Any], key: str) -> List[int]:
        lst = RouterInputParser._safe_list(raw, key)
        return [int(v) for v in lst if isinstance(v, int)]

    @staticmethod
    def _safe_str_list(raw: Dict[str, Any], key: str) -> List[str]:
        lst = RouterInputParser._safe_list(raw, key)
        return [str(v) for v in lst if isinstance(v, str)]

    # ---------- public entry ----------

    def parse(self, raw: Dict[str, object]) -> RouterInput:
        nodes_raw = self._safe_list(raw, "nodes")
        lines_raw = self._safe_list(raw, "lines")
        constraints_raw = self._safe_dict(raw, "constraints")
        meta = raw.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        return RouterInput(
            meta=meta,
            nodes=[self._parse_node(n) for n in nodes_raw if isinstance(n, dict)],
            lines=[self._parse_line(l) for l in lines_raw if isinstance(l, dict)],
            constraints=self._parse_constraints(constraints_raw),
            raw=raw,
        )

    # ---------- constraints ----------

    def _parse_constraints(self, raw: Dict[str, Any]) -> ConstraintsSpec:
        spatial_raw = self._safe_dict(raw, "spatial_rules")
        default_layers = self._safe_int_list(spatial_raw, "default_z_layers") or self.DEFAULT_Z_LAYERS
        spatial = SpatialRules(
            default_clearance_voxels=self._safe_int(
                spatial_raw, "default_clearance_voxels", self.DEFAULT_CLEARANCE_VOXELS
            ),
            max_search_radius_voxels=self._safe_int(
                spatial_raw, "max_search_radius_voxels", self.DEFAULT_MAX_SEARCH_RADIUS_VOXELS
            ),
            default_z_layers=default_layers,
        )
        return ConstraintsSpec(spatial_rules=spatial)

    # ---------- nodes ----------

    def _parse_node(self, raw: Dict[str, Any]) -> NodeSpec:
        loc_raw = self._safe_dict(raw, "location_2d")
        return NodeSpec(
            node_id=self._safe_str(raw, "id", "") or "",
            node_type=self._safe_str(raw, "type", "") or "",
            role=self._safe_str(raw, "role"),
            label=self._safe_str(raw, "label"),
            pid_tag=self._safe_str(raw, "pid_tag"),
            equipment_ref=self._safe_str(raw, "equipment_ref"),
            location_2d_x=self._safe_float(loc_raw, "x"),
            location_2d_y=self._safe_float(loc_raw, "y"),
            properties=self._safe_dict(raw, "properties"),
            placement_hint=self._parse_placement_hint(self._safe_dict(raw, "placement_hint")),
            bbox_hint=self._parse_bbox_hint(self._safe_dict(raw, "bbox_hint")),
        )

    def _parse_placement_hint(self, raw: Dict[str, Any]) -> PlacementHint:
        return PlacementHint(
            z_layers=self._safe_int_list(raw, "z_layers"),
            anchor_policy=self._safe_str(raw, "anchor_policy"),
            direction_preferred=self._safe_str(raw, "direction_preferred"),
        )

    def _parse_bbox_hint(self, raw: Dict[str, Any]) -> BBoxHint:
        return BBoxHint(
            extent_voxels=self._safe_int_list(raw, "extent_voxels"),
            clearance_voxels=self._safe_int(raw, "clearance_voxels"),
        )

    # ---------- lines ----------

    def _parse_line(self, raw: Dict[str, Any]) -> LineSpec:
        return LineSpec(
            line_id=self._safe_str(raw, "id", "") or "",
            tag=self._safe_str(raw, "tag"),
            from_node_id=self._safe_str(raw, "from_node", "") or "",
            to_node_id=self._safe_str(raw, "to_node", "") or "",
            via_node_ids=self._safe_str_list(raw, "via_nodes"),
            nominal_diameter_mm=self._safe_float(raw, "nominal_diameter_mm"),
            with_flanges=self._safe_bool(raw, "with_flanges"),
            raw=raw,
        )
