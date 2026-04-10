from __future__ import annotations

from typing import Dict

from .GenerationMetaBuilder import GenerationMetaBuilder
from .IJsonEmitter import IJsonEmitter
from .RouterInputModels import RouterInput
from .config import RouterConfig
from .constants import DEFAULT_MATERIAL_ID, DEFAULT_NOMINAL_DIAMETER_M, MM_TO_M
from .domain_types import LineRouteMap, PlacedNodeMap


class MinimalJsonEmitter(IJsonEmitter):
    """Emits meta + segments with debug voxel paths only (no Pipe/Elbow components)."""

    def __init__(self) -> None:
        self._meta = GenerationMetaBuilder()

    def emit(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
        config: RouterConfig,
    ) -> Dict[str, object]:
        meta = self._meta.build(config)
        segments: list[Dict[str, object]] = []
        for line in router_input.lines:
            line_id = line.line_id
            route = line_routes.get(line_id)
            if not route or not route.success or not route.voxel_path:
                continue
            from_port = line.from_node_id
            to_port = line.to_node_id
            nominal_mm = line.nominal_diameter_mm
            nominal_diameter_m = (
                float(nominal_mm) / MM_TO_M if nominal_mm is not None else DEFAULT_NOMINAL_DIAMETER_M
            )
            segments.append({
                "id": f"seg_{line_id}",
                "display_name": line.tag or line_id,
                "from_port": from_port,
                "to_port": to_port,
                "spec": {
                    "nominal_diameter": nominal_diameter_m,
                    "material_id": DEFAULT_MATERIAL_ID,
                    "with_flanges": bool(line.with_flanges),
                },
                "debug_voxel_path": [list(v) for v in route.voxel_path],
                "components": [],
            })
        return {
            "meta": meta,
            "materials": [],
            "assets": [],
            "tee_joints": [],
            "segments": segments,
        }
