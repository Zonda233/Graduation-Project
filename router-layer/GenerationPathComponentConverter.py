from __future__ import annotations

from typing import Dict, List

from .PipeAndTeeGeometryTrimmer import PipeAndTeeGeometryTrimmer
from .VoxelGeometryMaps import Vc, VoxelGeometryMaps
from .config import RouterConfig
from .constants import WC_PRECISION


class GenerationPathComponentConverter:
    """Converts a 6-neighbour voxel path into schema-oriented Pipe and Elbow component dicts."""

    def __init__(self, config: RouterConfig, trimmer: PipeAndTeeGeometryTrimmer) -> None:
        self._config = config
        self._trimmer = trimmer

    def convert(
        self,
        path: List[Vc],
        segment_id: str,
        nominal_diameter_m: float,
        straight_type: str = "Pipe",
    ) -> List[Dict[str, object]]:
        if len(path) < 2:
            return []
        components: List[Dict[str, object]] = []
        comp_index = 0
        axis_map = VoxelGeometryMaps.AXIS_BY_DELTA
        i = 0
        while i < len(path) - 1:
            start = path[i]
            delta = self._delta(path[i], path[i + 1])
            axis = axis_map.get(delta)
            if not axis:
                i += 1
                continue
            j = i + 1
            while j < len(path) - 1:
                d = self._delta(path[j], path[j + 1])
                if d != delta:
                    break
                j += 1
            end = path[j]
            length_m = self._config.voxel_size * (j - i)
            comp_id = f"{segment_id}_c{comp_index:02d}"
            comp_index += 1
            components.append(
                self._build_pipe_component(
                    comp_id=comp_id,
                    start=start,
                    end=end,
                    axis=axis,
                    length_m=length_m,
                    straight_type=straight_type,
                )
            )
            if j < len(path) - 1:
                next_delta = self._delta(path[j], path[j + 1])
                axis_out = axis_map.get(next_delta)
                if axis_out:
                    comp_id_elbow = f"{segment_id}_c{comp_index:02d}"
                    comp_index += 1
                    components.append(
                        self._build_elbow_component(
                            comp_id=comp_id_elbow,
                            center=path[j],
                            axis_in=axis,
                            axis_out=axis_out,
                        )
                    )
            i = j
        self._trimmer.trim_pipes_around_elbows(components, nominal_diameter_m)
        return components

    @staticmethod
    def _delta(a: Vc, b: Vc) -> Vc:
        return (b[0] - a[0], b[1] - a[1], b[2] - a[2])

    def _build_pipe_component(
        self,
        comp_id: str,
        start: Vc,
        end: Vc,
        axis: str,
        length_m: float,
        straight_type: str,
    ) -> Dict[str, object]:
        return {
            "comp_id": comp_id,
            "type": straight_type,
            "vc_start": list(start),
            "vc_end": list(end),
            "wc_start": VoxelGeometryMaps.vc_to_wc(start, self._config),
            "wc_end": VoxelGeometryMaps.vc_to_wc(end, self._config),
            "axis": axis,
            "length_m": round(length_m, WC_PRECISION),
        }

    def _build_elbow_component(
        self,
        comp_id: str,
        center: Vc,
        axis_in: str,
        axis_out: str,
    ) -> Dict[str, object]:
        return {
            "comp_id": comp_id,
            "type": "Elbow",
            "vc_center": list(center),
            "wc_center": VoxelGeometryMaps.vc_to_wc(center, self._config),
            "axis_in": axis_in,
            "axis_out": axis_out,
            "angle_deg": 90,
        }
