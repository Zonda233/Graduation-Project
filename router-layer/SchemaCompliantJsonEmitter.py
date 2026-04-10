from __future__ import annotations

from typing import Dict

from .GenerationMetaBuilder import GenerationMetaBuilder
from .IJsonEmitter import IJsonEmitter
from .PlaceholderTankAssetBuilder import PlaceholderTankAssetBuilder
from .RouterInputModels import RouterInput
from .SchemaDefaultMaterials import SchemaDefaultMaterials
from .SegmentsAndTeesAssembler import SegmentsAndTeesAssembler
from .config import RouterConfig
from .domain_types import LineRouteMap, PlacedNodeMap


class SchemaCompliantJsonEmitter(IJsonEmitter):
    """Emits generation-layer JSON that satisfies protocol_v1 schema (pipes, elbows, tees, materials)."""

    def __init__(self) -> None:
        self._meta = GenerationMetaBuilder()
        self._materials = SchemaDefaultMaterials()
        self._tank_builder = PlaceholderTankAssetBuilder()

    def emit(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
        config: RouterConfig,
    ) -> Dict[str, object]:
        meta = self._meta.build(config)
        assembler = SegmentsAndTeesAssembler(config)
        segments, tee_joints = assembler.build(router_input, placed_nodes, line_routes)
        assets = self._tank_builder.build(router_input, placed_nodes, config)
        return {
            "meta": meta,
            "materials": self._materials.carbon_steel_list(),
            "assets": assets,
            "tee_joints": tee_joints,
            "segments": segments,
        }
