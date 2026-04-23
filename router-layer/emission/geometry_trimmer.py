from __future__ import annotations

from typing import Dict, List, Optional

from ..config import RouterConfig
from ..constants import (
    TEE_PORT_SUFFIX_BRANCH,
    TEE_PORT_SUFFIX_RUN_A,
    TEE_PORT_SUFFIX_RUN_B,
    WC_PRECISION,
)
from ..grid.voxel_geometry import VoxelGeometryMaps


class PipeAndTeeGeometryTrimmer:
    """Adjusts Pipe wc endpoints at Elbows and Tee ports to match generation-layer geometry."""

    ELBOW_RADIUS_FACTOR = 1.5

    def __init__(self, config: RouterConfig) -> None:
        self._config = config

    def trim_pipes_around_elbows(
        self,
        components: List[Dict[str, object]],
        nominal_diameter_m: float,
    ) -> None:
        od = VoxelGeometryMaps.outer_diameter_m(nominal_diameter_m)
        bend_radius = self.ELBOW_RADIUS_FACTOR * od
        trim = bend_radius + self._config.elbow_overlap_m
        for idx, comp in enumerate(components):
            if comp.get("type") != "Elbow":
                continue
            corner = list(comp["wc_center"])  # type: ignore[list-item]
            axis_in = str(comp["axis_in"])
            axis_out = str(comp["axis_out"])
            comp["bend_radius_m"] = round(bend_radius, WC_PRECISION)
            if idx - 1 >= 0 and components[idx - 1].get("type") == "Pipe":
                prev_pipe = components[idx - 1]
                prev_pipe["wc_end"] = VoxelGeometryMaps.shift_wc(corner, axis_in, -trim)
                self._update_pipe_length_m(prev_pipe)
            if idx + 1 < len(components) and components[idx + 1].get("type") == "Pipe":
                next_pipe = components[idx + 1]
                next_pipe["wc_start"] = VoxelGeometryMaps.shift_wc(corner, axis_out, trim)
                self._update_pipe_length_m(next_pipe)

    @staticmethod
    def first_pipe(components: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
        for comp in components:
            if comp.get("type") == "Pipe":
                return comp
        return None

    @staticmethod
    def last_pipe(components: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
        for comp in reversed(components):
            if comp.get("type") == "Pipe":
                return comp
        return None

    def tee_port_wc(self, tee: Dict[str, object], port_id: str) -> Optional[List[float]]:
        wc_center = list(tee["wc_center"])  # type: ignore[list-item]
        spec = tee["spec"]  # type: ignore[assignment]
        main_d = float(spec["main_diameter"])  # type: ignore[index]
        main_od = VoxelGeometryMaps.outer_diameter_m(main_d)
        for port in tee.get("ports", []):  # type: ignore[union-attr]
            p = port  # type: Dict[str, object]
            if str(p.get("port_id")) != port_id:
                continue
            axis = str(p["axis"])
            if port_id.endswith("_branch"):
                offset_raw = self._config.tee_branch_half_length_factor * main_od
            else:
                offset_raw = self._config.tee_run_half_length_factor * main_od
            offset = min(offset_raw, self._config.voxel_size / 2.0)
            return VoxelGeometryMaps.shift_wc(wc_center, axis, offset)
        return None

    @staticmethod
    def tee_id_from_port(port_id: str) -> Optional[str]:
        if port_id.endswith(TEE_PORT_SUFFIX_RUN_A):
            return port_id[: -len(TEE_PORT_SUFFIX_RUN_A)]
        if port_id.endswith(TEE_PORT_SUFFIX_RUN_B):
            return port_id[: -len(TEE_PORT_SUFFIX_RUN_B)]
        if port_id.endswith(TEE_PORT_SUFFIX_BRANCH):
            return port_id[: -len(TEE_PORT_SUFFIX_BRANCH)]
        return None

    def trim_segment_pipes_to_tee_ports(
        self,
        segment: Dict[str, object],
        tee_map: Dict[str, Dict[str, object]],
    ) -> None:
        components = segment.get("components", [])
        if not isinstance(components, list) or not components:
            return
        from_port = segment.get("from_port")
        to_port = segment.get("to_port")
        if isinstance(from_port, str) and from_port.startswith("tee_"):
            tee_id = self.tee_id_from_port(from_port)
            tee = tee_map.get(tee_id or "")
            first = self.first_pipe(components)  # type: ignore[arg-type]
            if tee and first:
                wc = self.tee_port_wc(tee, from_port)
                if wc:
                    first["wc_start"] = wc
                    self._update_pipe_length_m(first)
        if isinstance(to_port, str) and to_port.startswith("tee_"):
            tee_id = self.tee_id_from_port(to_port)
            tee = tee_map.get(tee_id or "")
            last = self.last_pipe(components)  # type: ignore[arg-type]
            if tee and last:
                wc = self.tee_port_wc(tee, to_port)
                if wc:
                    last["wc_end"] = wc
                    self._update_pipe_length_m(last)

    @staticmethod
    def _update_pipe_length_m(pipe: Dict[str, object]) -> None:
        pipe["length_m"] = round(
            VoxelGeometryMaps.pipe_length_m(
                list(pipe["wc_start"]),  # type: ignore[arg-type]
                list(pipe["wc_end"]),  # type: ignore[arg-type]
            ),
            WC_PRECISION,
        )
