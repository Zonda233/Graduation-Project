from __future__ import annotations

from typing import Dict

from ..config import RouterConfig
from ..models.domain_types import LineRouteMap, PlacedNodeMap
from ..models.input_models import RouterInput
from .materials import SchemaDefaultMaterials
from .meta_builder import GenerationMetaBuilder
from .segments_assembler import SegmentsAndTeesAssembler


class SchemaCompliantJsonEmitter:
    """Emits generation-layer JSON that satisfies protocol_v1 schema (pipes, elbows, tees, materials)."""

    def __init__(self) -> None:
        self._meta = GenerationMetaBuilder()
        self._materials = SchemaDefaultMaterials()

    def emit(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
        config: RouterConfig,
    ) -> Dict[str, object]:
        # Import here to avoid circular dependency at module load time
        from ..assets.tank_builder import PlaceholderTankAssetBuilder
        from ..assets.instrument_builder import InstrumentAssetBuilder

        meta = self._meta.build(config)
        assembler = SegmentsAndTeesAssembler(config)
        segments, tee_joints = assembler.build(router_input, placed_nodes, line_routes)
        tank_assets = PlaceholderTankAssetBuilder().build(router_input, placed_nodes, config)
        instrument_assets = InstrumentAssetBuilder().build(router_input, placed_nodes)
        assets = tank_assets + instrument_assets
        return {
            "meta": meta,
            "materials": self._materials.carbon_steel_list(),
            "assets": assets,
            "tee_joints": tee_joints,
            "segments": segments,
        }
