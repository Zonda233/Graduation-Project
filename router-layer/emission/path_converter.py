from __future__ import annotations

from typing import Dict, List, Optional, Set

from ..config import RouterConfig
from ..constants import WC_PRECISION
from ..grid.voxel_geometry import VoxelGeometryMaps
from ..models.types import Vc
from .geometry_trimmer import PipeAndTeeGeometryTrimmer


class GenerationPathComponentConverter:
    """Converts a 6-neighbour voxel path into schema-oriented component dicts.

    Supports three component types beyond Pipe/Elbow:

    * ``SignalLine`` — straight segment for instrument signal lines.
    * ``Valve``     — injected at the midpoint voxel of the path when
                      *valve_subtype* is provided (Track B).
    * ``Reducer``   — injected at every voxel listed in *reducer_vcs*
                      (Track A, InlineReducer nodes).
    """

    def __init__(self, config: RouterConfig, trimmer: PipeAndTeeGeometryTrimmer) -> None:
        self._config = config
        self._trimmer = trimmer

    def convert(
        self,
        path: List[Vc],
        segment_id: str,
        nominal_diameter_m: float,
        straight_type: str = "Pipe",
        valve_subtype: Optional[str] = None,
        reducer_vcs: Optional[Dict[Vc, Dict[str, float]]] = None,
    ) -> List[Dict[str, object]]:
        """Convert *path* to a list of component dicts.

        Parameters
        ----------
        path:
            Ordered list of voxel coordinates from start to end.
        segment_id:
            Prefix used to generate unique ``comp_id`` values.
        nominal_diameter_m:
            Nominal pipe diameter in metres (used for elbow trimming).
        straight_type:
            Component type for straight runs — ``"Pipe"`` or ``"SignalLine"``.
        valve_subtype:
            When set (``"Gate"`` or ``"Ball"``), a single ``Valve`` component
            is injected at the midpoint voxel of the path, splitting the
            surrounding pipe segments at that voxel boundary.
        reducer_vcs:
            Mapping of voxel coordinate → ``{"diameter_in_m": …,
            "diameter_out_m": …}``.  A ``Reducer`` component is injected at
            each matching voxel, replacing the pipe segment at that position.
        """
        path = self._remove_immediate_backtracks(path)
        if len(path) < 2:
            return []

        # Determine which voxels require special component injection.
        special_vcs: Dict[Vc, str] = {}  # vc → component type tag
        reducer_map: Dict[Vc, Dict[str, float]] = reducer_vcs or {}
        for vc in reducer_map:
            special_vcs[vc] = "Reducer"

        valve_vc: Optional[Vc] = None
        if valve_subtype:
            mid_idx = len(path) // 2
            valve_vc = path[mid_idx]
            special_vcs[valve_vc] = "Valve"

        components: List[Dict[str, object]] = []
        comp_index = 0
        axis_map = VoxelGeometryMaps.AXIS_BY_DELTA

        # ------------------------------------------------------------------
        # Case A: special voxel at path[0] (reducer/valve is the start node).
        # Emit the special component first, then let the main loop handle the
        # rest of the path starting from path[1].
        # ------------------------------------------------------------------
        i = 0
        if path[0] in special_vcs and len(path) >= 2:
            start_vc = path[0]
            tag = special_vcs[start_vc]
            axis = axis_map.get(self._delta(path[0], path[1]))
            if axis:
                comp_id_special = f"{segment_id}_c{comp_index:02d}"
                comp_index += 1
                if tag == "Valve":
                    components.append(
                        self._build_valve_component(
                            comp_id=comp_id_special,
                            center=start_vc,
                            axis=axis,
                            nominal_diameter_m=nominal_diameter_m,
                            subtype=valve_subtype or "Gate",
                        )
                    )
                elif tag == "Reducer":
                    spec = reducer_map.get(start_vc, {})
                    components.append(
                        self._build_reducer_component(
                            comp_id=comp_id_special,
                            center=start_vc,
                            axis=axis,
                            diameter_in_m=spec.get("diameter_in_m", nominal_diameter_m),
                            diameter_out_m=spec.get("diameter_out_m", nominal_diameter_m),
                        )
                    )
                i = 1  # main loop starts from path[1]

        while i < len(path) - 1:
            start = path[i]
            delta = self._delta(path[i], path[i + 1])
            axis = axis_map.get(delta)
            if not axis:
                i += 1
                continue

            # Check if the *next* voxel (path[i+1]) is a special injection point.
            # If so, emit a single-voxel approach pipe up to that point, then the
            # special component, then continue from there.
            # Case B (middle): next_vc is not the last voxel — continue normally.
            # Case C (end):    next_vc IS the last voxel — emit approach pipe +
            #                  special component as the final two components.
            next_vc = path[i + 1]
            if next_vc in special_vcs:
                # Emit approach pipe from start → next_vc (1 voxel)
                length_m = self._config.voxel_size * 1
                comp_id = f"{segment_id}_c{comp_index:02d}"
                comp_index += 1
                components.append(
                    self._build_pipe_component(
                        comp_id=comp_id,
                        start=start,
                        end=next_vc,
                        axis=axis,
                        length_m=length_m,
                        straight_type=straight_type,
                    )
                )
                # Emit the special component at next_vc
                comp_id_special = f"{segment_id}_c{comp_index:02d}"
                comp_index += 1
                tag = special_vcs[next_vc]
                if tag == "Valve":
                    components.append(
                        self._build_valve_component(
                            comp_id=comp_id_special,
                            center=next_vc,
                            axis=axis,
                            nominal_diameter_m=nominal_diameter_m,
                            subtype=valve_subtype or "Gate",
                        )
                    )
                elif tag == "Reducer":
                    spec = reducer_map.get(next_vc, {})
                    components.append(
                        self._build_reducer_component(
                            comp_id=comp_id_special,
                            center=next_vc,
                            axis=axis,
                            diameter_in_m=spec.get("diameter_in_m", nominal_diameter_m),
                            diameter_out_m=spec.get("diameter_out_m", nominal_diameter_m),
                        )
                    )
                # Advance past the special voxel.  If next_vc was the last voxel
                # (Case C), i becomes len(path)-1 and the while-loop exits cleanly.
                i += 1
                continue

            # Normal run: extend straight segment as far as the direction holds.
            # Track *why* the loop stopped: "direction_change" or "special_voxel".
            j = i + 1
            stop_reason = "end_of_path"
            while j < len(path) - 1:
                # Stop before a special voxel so it gets its own component.
                if path[j + 1] in special_vcs:
                    stop_reason = "special_voxel"
                    break
                d = self._delta(path[j], path[j + 1])
                if d != delta:
                    stop_reason = "direction_change"
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
            # Only emit an Elbow when the run stopped because the direction
            # changed.  If it stopped because a special voxel (Valve/Reducer)
            # is next, no elbow is needed — the injection branch will handle
            # the next iteration.
            if stop_reason == "direction_change":
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

    @staticmethod
    def _remove_immediate_backtracks(path: List[Vc]) -> List[Vc]:
        if len(path) < 3:
            return list(path)
        simplified: List[Vc] = []
        for vc in path:
            if len(simplified) >= 2 and vc == simplified[-2]:
                simplified.pop()
                continue
            simplified.append(vc)
        return simplified

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

    def _build_valve_component(
        self,
        comp_id: str,
        center: Vc,
        axis: str,
        nominal_diameter_m: float,
        subtype: str,
    ) -> Dict[str, object]:
        """Build a Valve component dict at *center* voxel.

        The valve occupies one voxel; wc_start and wc_end are the two faces of
        that voxel along *axis*.
        """
        wc_center = VoxelGeometryMaps.vc_to_wc(center, self._config)
        half = self._config.voxel_size / 2.0
        vec = VoxelGeometryMaps.VEC_BY_AXIS[axis]
        wc_start = [round(wc_center[k] - vec[k] * half, WC_PRECISION) for k in range(3)]
        wc_end   = [round(wc_center[k] + vec[k] * half, WC_PRECISION) for k in range(3)]
        return {
            "comp_id": comp_id,
            "type": "Valve",
            "subtype": subtype,
            "vc_start": list(center),
            "vc_end": list(center),
            "wc_start": wc_start,
            "wc_end": wc_end,
            "axis": axis,
            "nominal_diameter": round(nominal_diameter_m, WC_PRECISION),
        }

    def _build_reducer_component(
        self,
        comp_id: str,
        center: Vc,
        axis: str,
        diameter_in_m: float,
        diameter_out_m: float,
    ) -> Dict[str, object]:
        """Build a Reducer component dict at *center* voxel.

        The reducer occupies one voxel; wc_start and wc_end are the two faces
        of that voxel along *axis*.
        """
        wc_center = VoxelGeometryMaps.vc_to_wc(center, self._config)
        half = self._config.voxel_size / 2.0
        vec = VoxelGeometryMaps.VEC_BY_AXIS[axis]
        wc_start = [round(wc_center[k] - vec[k] * half, WC_PRECISION) for k in range(3)]
        wc_end   = [round(wc_center[k] + vec[k] * half, WC_PRECISION) for k in range(3)]
        return {
            "comp_id": comp_id,
            "type": "Reducer",
            "vc_start": list(center),
            "vc_end": list(center),
            "wc_start": wc_start,
            "wc_end": wc_end,
            "axis": axis,
            "diameter_in_m": round(diameter_in_m, WC_PRECISION),
            "diameter_out_m": round(diameter_out_m, WC_PRECISION),
        }
