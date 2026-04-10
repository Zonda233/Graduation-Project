from __future__ import annotations

from typing import Dict, List

from .RouterInputModels import RouterInput
from .constants import DEFAULT_MATERIAL_ID
from .domain_types import PlacedNodeMap


class InstrumentAssetBuilder:
    """Builds Instrument assets from InlineInstrument nodes."""

    def build(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
    ) -> List[Dict[str, object]]:
        assets: List[Dict[str, object]] = []
        for node in router_input.nodes:
            if node.node_type != "InlineInstrument":
                continue
            placed = placed_nodes.get(node.node_id)
            if not placed:
                continue

            kind = str(node.properties.get("instrument_kind", "pressure_gauge"))
            if kind not in {"thermometer", "pressure_gauge"}:
                kind = "pressure_gauge"

            face_axis = node.placement_hint.direction_preferred or "+X"
            nominal_diameter = self._resolve_nominal_diameter(node.properties)
            wc = [round(v, 6) for v in placed.wc]

            assets.append(
                {
                    "id": node.node_id,
                    "type": "Instrument",
                    "display_name": node.label or node.pid_tag or node.node_id,
                    "instrument_kind": kind,
                    "wc_center": wc,
                    "material_id": DEFAULT_MATERIAL_ID,
                    "geometry": {
                        "face_axis": face_axis,
                    },
                    "ports": [
                        {
                            "port_id": node.node_id,
                            "role": "signal",
                            "vc": list(placed.vc),
                            "wc": wc,
                            "direction": face_axis,
                            "nominal_diameter": nominal_diameter,
                        }
                    ],
                }
            )
        return assets

    @staticmethod
    def _resolve_nominal_diameter(properties: Dict[str, object]) -> float:
        raw = properties.get("nominal_diameter_mm")
        try:
            mm = float(raw)
        except (TypeError, ValueError):
            return 0.006
        if mm <= 0.0:
            return 0.006
        return mm / 1000.0

