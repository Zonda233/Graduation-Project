from __future__ import annotations

from typing import Dict

from ..config import RouterConfig


class GenerationMetaBuilder:
    """Builds the generation-layer `meta` object shared by emitters."""

    GENERATOR_ID: str = "router_layer_seq_a_star"
    PROTOCOL_VERSION: str = "1.0.0"

    def build(self, config: RouterConfig) -> Dict[str, object]:
        return {
            "protocol_version": self.PROTOCOL_VERSION,
            "generator": self.GENERATOR_ID,
            "coordinate_system": {
                "type": "right_handed",
                "up_axis": "Z",
                "unit": "meter",
            },
            "voxel_grid": {
                "voxel_size": config.voxel_size,
                "origin_wc": list(config.origin_wc),
                "dimensions": list(config.grid_dimensions),
            },
        }
