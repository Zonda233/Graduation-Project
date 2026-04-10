from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .GenerationPathComponentConverter import GenerationPathComponentConverter
from .PipeAndTeeGeometryTrimmer import PipeAndTeeGeometryTrimmer
from .RouterInputModels import LineSpec, NodeSpec, RouterInput
from .VoxelGeometryMaps import Vc, VoxelGeometryMaps
from .config import RouterConfig
from .constants import (
    DEFAULT_MATERIAL_ID,
    DEFAULT_NOMINAL_DIAMETER_M,
    MM_TO_M,
    TEE_DEFAULT_AXES,
    TEE_ID_PREFIX,
    TEE_PORT_SUFFIX_BRANCH,
    TEE_PORT_SUFFIX_RUN_A,
    TEE_PORT_SUFFIX_RUN_B,
)
from .domain_types import LineRouteMap, PlacedNodeMap


@dataclass(frozen=True)
class _SegmentDescriptor:
    seg_id: str
    seg_from: str
    seg_to: str
    path_slice: List[Vc]
    line: LineSpec


class SegmentsAndTeesAssembler:
    """Splits routed lines at tee junctions and assembles segment + tee_joint JSON dicts."""

    def __init__(self, config: RouterConfig) -> None:
        self._config = config
        self._trimmer = PipeAndTeeGeometryTrimmer(config)
        self._path_converter = GenerationPathComponentConverter(config, self._trimmer)

    def build(
        self,
        router_input: RouterInput,
        placed_nodes: PlacedNodeMap,
        line_routes: LineRouteMap,
    ) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
        lines = list(router_input.lines)
        nodes = list(router_input.nodes)
        via_ids = self._collect_via_node_ids(lines, nodes)
        tee_id_by_via = self._build_tee_id_map(via_ids)

        seg_descriptors = self._build_segment_descriptors(
            lines=lines,
            line_routes=line_routes,
            placed_nodes=placed_nodes,
            tee_id_by_via=tee_id_by_via,
        )
        segment_by_id, tee_run_a_comp, tee_run_b_comp, tee_branch_comp = self._build_segments(seg_descriptors)
        tee_axes = self._build_tee_axes(via_ids, tee_id_by_via, lines, line_routes, placed_nodes)
        tee_joints = self._build_tee_joints(
            via_ids=via_ids,
            tee_id_by_via=tee_id_by_via,
            tee_axes=tee_axes,
            placed_nodes=placed_nodes,
            segment_by_id=segment_by_id,
            tee_run_a_comp=tee_run_a_comp,
            tee_run_b_comp=tee_run_b_comp,
            tee_branch_comp=tee_branch_comp,
        )

        tee_map = {str(tee["tee_id"]): tee for tee in tee_joints}
        for seg in segment_by_id.values():
            self._trimmer.trim_segment_pipes_to_tee_ports(seg, tee_map)
        return list(segment_by_id.values()), tee_joints

    def _collect_via_node_ids(self, lines: List[LineSpec], nodes: List[NodeSpec]) -> List[str]:
        via_ids: List[str] = []
        seen: Set[str] = set()
        junction_ids = {n.node_id for n in nodes if n.node_type == "Junction"}
        node_ids = {n.node_id for n in nodes}

        for line in lines:
            for via_id in line.via_node_ids:
                if via_id in seen:
                    continue
                seen.add(via_id)
                via_ids.append(via_id)

            from_node = line.from_node_id
            if from_node and from_node not in seen and from_node in node_ids and from_node in junction_ids:
                seen.add(from_node)
                via_ids.append(from_node)
        return via_ids

    def _build_tee_id_map(self, via_ids: List[str]) -> Dict[str, str]:
        return {vid: f"{TEE_ID_PREFIX}{idx + 1:02d}" for idx, vid in enumerate(via_ids)}

    def _build_segment_descriptors(
        self,
        lines: List[LineSpec],
        line_routes: LineRouteMap,
        placed_nodes: PlacedNodeMap,
        tee_id_by_via: Dict[str, str],
    ) -> List[_SegmentDescriptor]:
        descriptors: List[_SegmentDescriptor] = []
        for line in lines:
            route = line_routes.get(line.line_id)
            if not route or not route.success or not route.voxel_path:
                continue

            path = route.voxel_path
            if not line.via_node_ids:
                descriptors.append(
                    _SegmentDescriptor(
                        seg_id=f"seg_{line.line_id}",
                        seg_from=self._resolve_start_port(line.from_node_id, tee_id_by_via),
                        seg_to=line.to_node_id or "",
                        path_slice=path,
                        line=line,
                    )
                )
                continue

            via_nodes = list(line.via_node_ids)
            via_vcs = [placed_nodes[nid].vc for nid in via_nodes if nid in placed_nodes]
            slices = self._split_path_by_via(path, via_vcs)
            for index, path_slice in enumerate(slices):
                seg_from, seg_to = self._resolve_segment_ports_for_slice(
                    index=index,
                    from_port=line.from_node_id,
                    to_port=line.to_node_id,
                    via_nodes=via_nodes,
                    tee_id_by_via=tee_id_by_via,
                )
                seg_id = self._segment_id_for_slice(line.line_id, index, len(slices))
                descriptors.append(
                    _SegmentDescriptor(
                        seg_id=seg_id,
                        seg_from=seg_from,
                        seg_to=seg_to,
                        path_slice=path_slice,
                        line=line,
                    )
                )
        return descriptors

    def _build_segments(
        self,
        descriptors: List[_SegmentDescriptor],
    ) -> Tuple[Dict[str, Dict[str, object]], Dict[str, str], Dict[str, str], Dict[str, str]]:
        segment_by_id: Dict[str, Dict[str, object]] = {}
        tee_run_a_comp: Dict[str, str] = {}
        tee_run_b_comp: Dict[str, str] = {}
        tee_branch_comp: Dict[str, str] = {}

        for desc in descriptors:
            nominal_diameter_m = self._nominal_m(desc.line.nominal_diameter_mm)
            components = self._path_converter.convert(desc.path_slice, desc.seg_id, nominal_diameter_m)
            if not components:
                continue

            self._link_tee_component_refs(
                desc=desc,
                first_comp_id=str(components[0]["comp_id"]),
                last_comp_id=str(components[-1]["comp_id"]),
                tee_run_a_comp=tee_run_a_comp,
                tee_run_b_comp=tee_run_b_comp,
                tee_branch_comp=tee_branch_comp,
            )

            segment_by_id[desc.seg_id] = {
                "id": desc.seg_id,
                "display_name": desc.line.tag or desc.line.line_id,
                "from_port": desc.seg_from,
                "to_port": desc.seg_to,
                "spec": {
                    "nominal_diameter": nominal_diameter_m,
                    "material_id": DEFAULT_MATERIAL_ID,
                    "with_flanges": bool(desc.line.with_flanges),
                },
                "components": components,
            }
        return segment_by_id, tee_run_a_comp, tee_run_b_comp, tee_branch_comp

    def _build_tee_axes(
        self,
        via_ids: List[str],
        tee_id_by_via: Dict[str, str],
        lines: List[LineSpec],
        line_routes: LineRouteMap,
        placed_nodes: PlacedNodeMap,
    ) -> Dict[str, Dict[str, str]]:
        tee_axes: Dict[str, Dict[str, str]] = {}
        axis_map = VoxelGeometryMaps.AXIS_BY_DELTA

        for via_id in via_ids:
            tee_id = tee_id_by_via[via_id]
            tee_vc = placed_nodes[via_id].vc
            run_a_axis: Optional[str] = None
            run_b_axis: Optional[str] = None
            branch_axis: Optional[str] = None

            for line in lines:
                route = line_routes.get(line.line_id)
                if not route or not route.voxel_path:
                    continue

                path = route.voxel_path
                at_endpoint = line.from_node_id == via_id or line.to_node_id == via_id
                if not at_endpoint and via_id in line.via_node_ids:
                    idx = self._index_in_path(path, tee_vc)
                    if idx is None or idx <= 0 or idx >= len(path) - 1:
                        continue
                    prev_vc = path[idx - 1]
                    next_vc = path[idx + 1]
                    run_a_axis = axis_map.get(VoxelGeometryMaps.delta_vc(prev_vc, tee_vc))
                    run_b_axis = axis_map.get(VoxelGeometryMaps.delta_vc(next_vc, tee_vc))
                elif line.from_node_id == via_id and len(path) >= 2 and path[0] == tee_vc:
                    branch_axis = axis_map.get(VoxelGeometryMaps.delta_vc(path[1], tee_vc))

            tee_axes[tee_id] = {
                "run_a": run_a_axis or TEE_DEFAULT_AXES["run_a"],
                "run_b": run_b_axis or TEE_DEFAULT_AXES["run_b"],
                "branch": branch_axis or TEE_DEFAULT_AXES["branch"],
            }
        return tee_axes

    def _build_tee_joints(
        self,
        via_ids: List[str],
        tee_id_by_via: Dict[str, str],
        tee_axes: Dict[str, Dict[str, str]],
        placed_nodes: PlacedNodeMap,
        segment_by_id: Dict[str, Dict[str, object]],
        tee_run_a_comp: Dict[str, str],
        tee_run_b_comp: Dict[str, str],
        tee_branch_comp: Dict[str, str],
    ) -> List[Dict[str, object]]:
        tee_joints: List[Dict[str, object]] = []
        for via_id in via_ids:
            tee_id = tee_id_by_via[via_id]
            placed = placed_nodes.get(via_id)
            if not placed:
                continue

            axes = tee_axes.get(tee_id, dict(TEE_DEFAULT_AXES))
            main_diameter, branch_diameter = self._resolve_tee_diameters(tee_id, segment_by_id)
            tee_joints.append(
                {
                    "tee_id": tee_id,
                    "vc_center": list(placed.vc),
                    "wc_center": VoxelGeometryMaps.vc_to_wc(placed.vc, self._config),
                    "ports": [
                        {
                            "port_id": f"{tee_id}{TEE_PORT_SUFFIX_RUN_A}",
                            "axis": axes["run_a"],
                            "connects_to_comp": tee_run_a_comp.get(tee_id, ""),
                        },
                        {
                            "port_id": f"{tee_id}{TEE_PORT_SUFFIX_RUN_B}",
                            "axis": axes["run_b"],
                            "connects_to_comp": tee_run_b_comp.get(tee_id, ""),
                        },
                        {
                            "port_id": f"{tee_id}{TEE_PORT_SUFFIX_BRANCH}",
                            "axis": axes["branch"],
                            "connects_to_comp": tee_branch_comp.get(tee_id, ""),
                        },
                    ],
                    "spec": {
                        "main_diameter": main_diameter,
                        "branch_diameter": branch_diameter,
                        "material_id": DEFAULT_MATERIAL_ID,
                    },
                }
            )
        return tee_joints

    @staticmethod
    def _resolve_start_port(from_port: str, tee_id_by_via: Dict[str, str]) -> str:
        if from_port in tee_id_by_via:
            return f"{tee_id_by_via[from_port]}{TEE_PORT_SUFFIX_BRANCH}"
        return from_port or ""

    @staticmethod
    def _split_path_by_via(path: List[Vc], via_vcs: List[Vc]) -> List[List[Vc]]:
        slices: List[List[Vc]] = []
        start_index = 0
        for vc in via_vcs:
            try:
                split_index = path.index(vc, start_index)
            except ValueError:
                break
            slices.append(path[start_index : split_index + 1])
            start_index = split_index
        if start_index < len(path):
            slices.append(path[start_index:])
        return slices

    @staticmethod
    def _resolve_segment_ports_for_slice(
        index: int,
        from_port: str,
        to_port: str,
        via_nodes: List[str],
        tee_id_by_via: Dict[str, str],
    ) -> Tuple[str, str]:
        if index == 0:
            return (
                from_port or "",
                f"{tee_id_by_via[via_nodes[0]]}{TEE_PORT_SUFFIX_RUN_A}",
            )

        seg_from = f"{tee_id_by_via[via_nodes[index - 1]]}{TEE_PORT_SUFFIX_RUN_B}"
        if index < len(via_nodes):
            seg_to = f"{tee_id_by_via[via_nodes[index]]}{TEE_PORT_SUFFIX_RUN_A}"
        else:
            seg_to = to_port or ""
        return seg_from, seg_to

    @staticmethod
    def _segment_id_for_slice(line_id: str, index: int, total_slices: int) -> str:
        if total_slices <= 1:
            return f"seg_{line_id}"
        return f"seg_{line_id}_{index + 1}"

    @staticmethod
    def _nominal_m(nominal_mm: Optional[float]) -> float:
        if nominal_mm is None:
            return DEFAULT_NOMINAL_DIAMETER_M
        return float(nominal_mm) / MM_TO_M

    @staticmethod
    def _link_tee_component_refs(
        desc: _SegmentDescriptor,
        first_comp_id: str,
        last_comp_id: str,
        tee_run_a_comp: Dict[str, str],
        tee_run_b_comp: Dict[str, str],
        tee_branch_comp: Dict[str, str],
    ) -> None:
        if desc.seg_to.endswith(TEE_PORT_SUFFIX_RUN_A):
            tee_id = desc.seg_to[: -len(TEE_PORT_SUFFIX_RUN_A)]
            tee_run_a_comp[tee_id] = last_comp_id
        if desc.seg_from.endswith(TEE_PORT_SUFFIX_RUN_B):
            tee_id = desc.seg_from[: -len(TEE_PORT_SUFFIX_RUN_B)]
            tee_run_b_comp[tee_id] = first_comp_id
        if desc.seg_from.endswith(TEE_PORT_SUFFIX_BRANCH):
            tee_id = desc.seg_from[: -len(TEE_PORT_SUFFIX_BRANCH)]
            tee_branch_comp[tee_id] = first_comp_id

    @staticmethod
    def _index_in_path(path: List[Vc], vc: Vc) -> Optional[int]:
        try:
            return path.index(vc)
        except ValueError:
            return None

    def _resolve_tee_diameters(
        self,
        tee_id: str,
        segment_by_id: Dict[str, Dict[str, object]],
    ) -> Tuple[float, float]:
        main_diameter = DEFAULT_NOMINAL_DIAMETER_M
        branch_diameter = DEFAULT_NOMINAL_DIAMETER_M

        run_a_port = f"{tee_id}{TEE_PORT_SUFFIX_RUN_A}"
        run_b_port = f"{tee_id}{TEE_PORT_SUFFIX_RUN_B}"
        branch_port = f"{tee_id}{TEE_PORT_SUFFIX_BRANCH}"

        for seg in segment_by_id.values():
            to_port = str(seg["to_port"])
            from_port = str(seg["from_port"])
            if to_port == run_a_port or from_port == run_b_port:
                spec = seg.get("spec")
                if isinstance(spec, dict):
                    main_diameter = float(spec["nominal_diameter"])  # type: ignore[arg-type]
                break

        for seg in segment_by_id.values():
            if str(seg["from_port"]) == branch_port:
                spec = seg.get("spec")
                if isinstance(spec, dict):
                    branch_diameter = float(spec["nominal_diameter"])  # type: ignore[arg-type]
                break

        return main_diameter, branch_diameter
