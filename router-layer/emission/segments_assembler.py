from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

log = logging.getLogger(__name__)

from ..config import RouterConfig
from ..constants import (
    DEFAULT_MATERIAL_ID,
    DEFAULT_NOMINAL_DIAMETER_M,
    MM_TO_M,
    TEE_DEFAULT_AXES,
    TEE_ID_PREFIX,
    TEE_PORT_SUFFIX_BRANCH,
    TEE_PORT_SUFFIX_RUN_A,
    TEE_PORT_SUFFIX_RUN_B,
)
from ..grid.voxel_geometry import VoxelGeometryMaps
from ..models.domain_types import LineRouteMap, PlacedNodeMap
from ..models.input_models import LineSpec, NodeSpec, RouterInput
from ..models.types import Vc
from .geometry_trimmer import PipeAndTeeGeometryTrimmer
from .path_converter import GenerationPathComponentConverter


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

        # Tee axes must be computed first so that _build_segment_descriptors can
        # correctly assign _run_a / _run_b / _branch to junction-endpoint lines.
        tee_axes = self._build_tee_axes(via_ids, tee_id_by_via, lines, line_routes, placed_nodes)

        seg_descriptors = self._build_segment_descriptors(
            lines=lines,
            line_routes=line_routes,
            placed_nodes=placed_nodes,
            tee_id_by_via=tee_id_by_via,
            tee_axes=tee_axes,
        )
        segment_by_id, tee_run_a_comp, tee_run_b_comp, tee_branch_comp = self._build_segments(
            seg_descriptors,
            placed_nodes=placed_nodes,
            nodes=nodes,
        )
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

            # Collect junction nodes that appear as line endpoints (from or to).
            # These become tee joints even when the junction is not a via node.
            for endpoint in (line.from_node_id, line.to_node_id):
                if endpoint and endpoint not in seen and endpoint in node_ids and endpoint in junction_ids:
                    seen.add(endpoint)
                    via_ids.append(endpoint)
        return via_ids

    def _build_tee_id_map(self, via_ids: List[str]) -> Dict[str, str]:
        return {vid: f"{TEE_ID_PREFIX}{idx + 1:02d}" for idx, vid in enumerate(via_ids)}

    def _build_segment_descriptors(
        self,
        lines: List[LineSpec],
        line_routes: LineRouteMap,
        placed_nodes: PlacedNodeMap,
        tee_id_by_via: Dict[str, str],
        tee_axes: Dict[str, Dict[str, str]],
    ) -> List[_SegmentDescriptor]:
        descriptors: List[_SegmentDescriptor] = []
        for line in lines:
            route = line_routes.get(line.line_id)
            if not route or not route.success or not route.voxel_path:
                continue

            path = route.voxel_path
            if not line.via_node_ids:
                seg_from = self._resolve_endpoint_port(
                    node_id=line.from_node_id,
                    tee_id_by_via=tee_id_by_via,
                    tee_axes=tee_axes,
                    path=path,
                    is_from=True,
                    placed_nodes=placed_nodes,
                )
                seg_to = self._resolve_endpoint_port(
                    node_id=line.to_node_id or "",
                    tee_id_by_via=tee_id_by_via,
                    tee_axes=tee_axes,
                    path=path,
                    is_from=False,
                    placed_nodes=placed_nodes,
                )
                descriptors.append(
                    _SegmentDescriptor(
                        seg_id=f"seg_{line.line_id}",
                        seg_from=seg_from,
                        seg_to=seg_to,
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
        placed_nodes: Optional["PlacedNodeMap"] = None,
        nodes: Optional[List[NodeSpec]] = None,
    ) -> Tuple[Dict[str, Dict[str, object]], Dict[str, str], Dict[str, str], Dict[str, str]]:
        segment_by_id: Dict[str, Dict[str, object]] = {}
        tee_run_a_comp: Dict[str, str] = {}
        tee_run_b_comp: Dict[str, str] = {}
        tee_branch_comp: Dict[str, str] = {}

        # Build a map of InlineReducer voxel → diameter spec for quick lookup.
        reducer_vc_map: Dict[Vc, Dict[str, float]] = {}
        if placed_nodes and nodes:
            for node in nodes:
                if node.node_type != "InlineReducer":
                    continue
                if node.node_id not in placed_nodes:
                    continue
                vc = placed_nodes[node.node_id].vc
                props = node.properties
                diameter_in = float(props.get("nominal_diameter_in_mm", 80)) / MM_TO_M
                diameter_out = float(props.get("nominal_diameter_out_mm", 50)) / MM_TO_M
                reducer_vc_map[vc] = {
                    "diameter_in_m": diameter_in,
                    "diameter_out_m": diameter_out,
                }

        for desc in descriptors:
            nominal_diameter_m = self._nominal_m(desc.line.nominal_diameter_mm)
            straight_type = "SignalLine" if self._is_instrument_signal_line(desc.line) else "Pipe"
            valve_subtype = self._valve_subtype(desc.line)

            # Collect reducer voxels that lie on this path slice.
            path_set = set(desc.path_slice)
            segment_reducer_vcs = {
                vc: spec for vc, spec in reducer_vc_map.items() if vc in path_set
            }

            components = self._path_converter.convert(
                desc.path_slice,
                desc.seg_id,
                nominal_diameter_m,
                straight_type=straight_type,
                valve_subtype=valve_subtype,
                reducer_vcs=segment_reducer_vcs if segment_reducer_vcs else None,
            )
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

    @staticmethod
    def _is_instrument_signal_line(line: LineSpec) -> bool:
        service = str(line.raw.get("service", "")).strip().lower()
        return service == "instrument_signal"

    @staticmethod
    def _valve_subtype(line: LineSpec) -> Optional[str]:
        """Return the valve subtype string if the line has one, else None."""
        raw_val = line.raw.get("valve_subtype")
        if not raw_val:
            return None
        val = str(raw_val).strip()
        return val if val in ("Gate", "Ball") else None

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
            # Count how many lines depart from this tee (junction-endpoint topology).
            # The first departure is classified as run_b (main run continuation);
            # the second departure is classified as branch.
            departure_count = 0

            for line in lines:
                route = line_routes.get(line.line_id)
                if not route or not route.voxel_path:
                    continue

                path = route.voxel_path
                if via_id in line.via_node_ids:
                    # via-node topology: tee sits in the middle of the path.
                    idx = self._index_in_path(path, tee_vc)
                    if idx is None or idx <= 0 or idx >= len(path) - 1:
                        continue
                    prev_vc = path[idx - 1]
                    next_vc = path[idx + 1]
                    # delta_vc(a, b) = a - b, so delta_vc(prev, tee) points FROM tee TOWARD prev.
                    # This gives the outward direction of the run_a port (facing the upstream pipe).
                    run_a_axis = axis_map.get(VoxelGeometryMaps.delta_vc(prev_vc, tee_vc))
                    # Similarly, delta_vc(next, tee) points FROM tee TOWARD next — the run_b port direction.
                    run_b_axis = axis_map.get(VoxelGeometryMaps.delta_vc(next_vc, tee_vc))
                elif line.to_node_id == via_id and len(path) >= 2 and path[-1] == tee_vc:
                    # junction-endpoint topology: a line ends at the tee.
                    # The run_a port faces the arriving pipe (direction FROM tee TOWARD prev voxel).
                    run_a_axis = axis_map.get(VoxelGeometryMaps.delta_vc(path[-2], tee_vc))
                elif line.from_node_id == via_id and len(path) >= 2 and path[0] == tee_vc:
                    # junction-endpoint topology: a line starts at the tee.
                    # The first departure line is the main run continuation (run_b).
                    # The second departure line is the branch.
                    # Using departure_count to distinguish them avoids the bug where
                    # two lines both starting at the tee would overwrite branch_axis
                    # with the second line's direction, losing the first line's axis.
                    depart_axis = axis_map.get(VoxelGeometryMaps.delta_vc(path[1], tee_vc))
                    if departure_count == 0:
                        run_b_axis = depart_axis
                    else:
                        branch_axis = depart_axis
                    departure_count += 1

            tee_axes[tee_id] = self._normalize_tee_axes(
                tee_id, run_a_axis, run_b_axis, branch_axis
            )
        return tee_axes

    @staticmethod
    def _normalize_tee_axes(
        tee_id: str,
        run_a_axis: Optional[str],
        run_b_axis: Optional[str],
        branch_axis: Optional[str],
    ) -> Dict[str, str]:
        """
        Validate and repair tee axis assignments.

        Rules
        -----
        1. run_a and run_b are kept as-is when both were computed from the path.
           They do NOT need to be anti-parallel — a tee can sit at an L-shaped
           bend in the main run (e.g. run_a="-X", run_b="+Y").
        2. Only when run_b was NOT computed from the path AND run_a is known do
           we infer run_b = opposite(run_a) as a straight-through fallback.
           This prevents silently overwriting a valid L-shaped run_b axis.
        3. branch must not collide with run_a or run_b; if it does, pick the
           first available axis.
        4. All three axes must be distinct; log a WARNING if any collision
           remains after repair.
        """
        opposite = {
            "+X": "-X", "-X": "+X",
            "+Y": "-Y", "-Y": "+Y",
            "+Z": "-Z", "-Z": "+Z",
        }
        run_a  = run_a_axis  or TEE_DEFAULT_AXES["run_a"]
        branch = branch_axis or TEE_DEFAULT_AXES["branch"]

        # Rule 2: infer run_b only when it was not computed from the path.
        # If run_b_axis is None the path did not provide it; use opposite(run_a)
        # as a straight-through guess.  If run_b_axis was computed, use it
        # directly — even if it is not anti-parallel to run_a (L-shaped tee).
        if run_b_axis is not None:
            run_b = run_b_axis
        elif run_a_axis is not None:
            run_b = opposite.get(run_a, TEE_DEFAULT_AXES["run_b"])
        else:
            run_b = TEE_DEFAULT_AXES["run_b"]

        # Rule 3: branch must not collide with either run axis.
        if branch in {run_a, run_b}:
            for candidate in ("+Y", "-Y", "+Z", "-Z", "+X", "-X"):
                if candidate not in {run_a, run_b}:
                    branch = candidate
                    break

        # Rule 4: warn if any two axes are still identical (degenerate tee).
        if len({run_a, run_b, branch}) < 3:
            log.warning(
                "Tee %r has degenerate axis assignment after normalisation: "
                "run_a=%r run_b=%r branch=%r.  "
                "Check that the via-node path passes through the tee voxel correctly.",
                tee_id, run_a, run_b, branch,
            )

        # Warn when run_a and run_b are not anti-parallel (L-shaped main run).
        # This is geometrically valid but unusual; log it so it is easy to spot.
        if opposite.get(run_a) != run_b:
            log.warning(
                "Tee %r has a non-straight main run: run_a=%r run_b=%r "
                "(they are not anti-parallel).  "
                "This is valid for an L-shaped junction but verify the path is correct.",
                tee_id, run_a, run_b,
            )

        return {"run_a": run_a, "run_b": run_b, "branch": branch}

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
        """Legacy helper used only by _resolve_segment_ports_for_slice (via-node topology).

        For junction-endpoint topology (no via_node_ids) use _resolve_endpoint_port
        instead, which correctly distinguishes _run_b from _branch.
        """
        if from_port in tee_id_by_via:
            return f"{tee_id_by_via[from_port]}{TEE_PORT_SUFFIX_BRANCH}"
        return from_port or ""

    def _resolve_endpoint_port(
        self,
        node_id: str,
        tee_id_by_via: Dict[str, str],
        tee_axes: Dict[str, Dict[str, str]],
        path: List[Vc],
        is_from: bool,
        placed_nodes: "PlacedNodeMap",
    ) -> str:
        """Resolve a segment's from_port or to_port for a junction-endpoint line.

        When the node is a junction (tee), we use the path direction relative to
        the tee's computed axes to assign the correct port suffix:

        * ``is_from=True``  (line starts at tee): compare departure direction
          against ``run_b`` axis → assign ``_run_b`` if they match, else ``_branch``.
        * ``is_from=False`` (line ends at tee): compare arrival direction
          against ``run_a`` axis → assign ``_run_a`` if they match, else ``_branch``.

        Falls back to the raw node ID when the node is not a tee junction.
        """
        if node_id not in tee_id_by_via:
            return node_id or ""

        tee_id = tee_id_by_via[node_id]
        axes = tee_axes.get(tee_id, {})
        placed = placed_nodes.get(node_id)
        axis_map = VoxelGeometryMaps.AXIS_BY_DELTA

        if is_from:
            # Pipe departs from the tee: first step of path is tee_vc → next_vc.
            if placed and len(path) >= 2 and path[0] == placed.vc:
                depart_axis = axis_map.get(VoxelGeometryMaps.delta_vc(path[1], placed.vc))
                if depart_axis and depart_axis == axes.get("run_b"):
                    return f"{tee_id}{TEE_PORT_SUFFIX_RUN_B}"
            return f"{tee_id}{TEE_PORT_SUFFIX_BRANCH}"
        else:
            # Pipe arrives at the tee: last step of path is prev_vc → tee_vc.
            if placed and len(path) >= 2 and path[-1] == placed.vc:
                arrive_axis = axis_map.get(VoxelGeometryMaps.delta_vc(path[-2], placed.vc))
                # run_a axis points FROM tee TOWARD the upstream pipe, which is
                # the same direction as the last path step (prev → tee reversed).
                if arrive_axis and arrive_axis == axes.get("run_a"):
                    return f"{tee_id}{TEE_PORT_SUFFIX_RUN_A}"
            return f"{tee_id}{TEE_PORT_SUFFIX_BRANCH}"

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
