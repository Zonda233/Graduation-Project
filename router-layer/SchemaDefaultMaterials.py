from __future__ import annotations

from typing import Dict, List

from .constants import DEFAULT_MATERIAL_ID


class SchemaDefaultMaterials:
    """Default `materials[]` entries required for router-emitted `spec.material_id` references."""

    @staticmethod
    def carbon_steel_list() -> List[Dict[str, object]]:
        return [
            {
                "id": DEFAULT_MATERIAL_ID,
                "display_name": "碳钢",
                "visual": {
                    "base_color": [0.4, 0.4, 0.45, 1.0],
                    "metallic": 0.9,
                    "roughness": 0.4,
                },
            },
        ]
