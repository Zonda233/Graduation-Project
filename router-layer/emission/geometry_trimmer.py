from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ..config import RouterConfig
from ..constants import (
    TEE_PORT_SUFFIX_BRANCH,
    TEE_PORT_SUFFIX_RUN_A,
    TEE_PORT_SUFFIX_RUN_B,
    WC_PRECISION,
)
from ..grid.voxel_geometry import VoxelGeometryMaps

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_AXIS_OPPOSITE: Dict[str, str] = {
    "+X": "-X", "-X": "+X",
    "+Y": "-Y", "-Y": "+Y",
    "+Z": "-Z", "-Z": "+Z",
}


def _opposite_axis(axis: str) -> str:
    """Return the axis string pointing in the opposite direction."""
    try:
        return _AXIS_OPPOSITE[axis]
    except KeyError:
        raise ValueError(f"Unknown axis string: {axis!r}") from None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

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
        self.trim_pipes_around_inline_components(components)

    # ------------------------------------------------------------------
    # Valve / Reducer face trimming
    # ------------------------------------------------------------------

    _INLINE_TYPES = frozenset({"Valve", "Reducer"})

    def trim_pipes_around_inline_components(
        self,
        components: List[Dict[str, object]],
    ) -> None:
        """Trim pipes adjacent to Valve or Reducer components to their faces.

        A Valve/Reducer occupies exactly one voxel.  Its ``wc_start`` and
        ``wc_end`` are the two face centres of that voxel along the flow axis.
        The pipe immediately *before* the component must end at ``wc_start``
        (not at the voxel centre), and the pipe immediately *after* must start
        at ``wc_end``.

        This pass runs **after** :meth:`trim_pipes_around_elbows` so that
        elbow trimming on the same pipe is not undone.
        """
        for idx, comp in enumerate(components):
            if comp.get("type") not in self._INLINE_TYPES:
                continue
            comp_wc_start = list(comp["wc_start"])  # type: ignore[list-item]
            comp_wc_end   = list(comp["wc_end"])    # type: ignore[list-item]

            # The pipe immediately before this component ends at wc_start.
            if idx - 1 >= 0 and components[idx - 1].get("type") == "Pipe":
                prev_pipe = components[idx - 1]
                prev_pipe["wc_end"] = comp_wc_start
                self._update_pipe_length_m(prev_pipe)
                log.debug(
                    "Trimmed %s wc_end to %s face of %s %s",
                    prev_pipe.get("comp_id"),
                    comp.get("type"),
                    comp.get("comp_id"),
                    comp_wc_start,
                )

            # The pipe immediately after this component starts at wc_end.
            if idx + 1 < len(components) and components[idx + 1].get("type") == "Pipe":
                next_pipe = components[idx + 1]
                next_pipe["wc_start"] = comp_wc_end
                self._update_pipe_length_m(next_pipe)
                log.debug(
                    "Trimmed %s wc_start to %s face of %s %s",
                    next_pipe.get("comp_id"),
                    comp.get("type"),
                    comp.get("comp_id"),
                    comp_wc_end,
                )

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

    def tee_offset_m(self, tee: Dict[str, object], port_id: str) -> float:
        """Return the half-length offset (metres) for the given tee port.

        The offset is capped at half a voxel so the pipe end never overshoots
        the adjacent voxel centre.
        """
        spec = tee["spec"]  # type: ignore[assignment]
        main_d = float(spec["main_diameter"])  # type: ignore[index]
        main_od = VoxelGeometryMaps.outer_diameter_m(main_d)
        if port_id.endswith("_branch"):
            offset_raw = self._config.tee_branch_half_length_factor * main_od
        else:
            offset_raw = self._config.tee_run_half_length_factor * main_od
        return min(offset_raw, self._config.voxel_size / 2.0)

    def tee_port_wc(self, tee: Dict[str, object], port_id: str) -> Optional[List[float]]:
        """Return the world-coordinate position of a tee port face centre.

        The position is computed by shifting ``wc_center`` along the **tee
        port's own axis** (as stored in the tee JSON).  This is the correct
        position for the tee mesh stub end.

        .. warning::
            Do **not** use this to set a connecting pipe's ``wc_start`` /
            ``wc_end`` unless you have verified that the pipe's travel axis
            matches the tee port axis.  Use
            :meth:`tee_port_wc_for_pipe` instead.
        """
        wc_center = list(tee["wc_center"])  # type: ignore[list-item]
        for port in tee.get("ports", []):  # type: ignore[union-attr]
            p = port  # type: Dict[str, object]
            if str(p.get("port_id")) != port_id:
                continue
            axis = str(p["axis"])
            offset = self.tee_offset_m(tee, port_id)
            return VoxelGeometryMaps.shift_wc(wc_center, axis, offset)
        return None

    def tee_port_wc_for_pipe(
        self,
        tee: Dict[str, object],
        port_id: str,
        pipe_axis: str,
        *,
        arriving: bool = False,
    ) -> List[float]:
        """Return the wc position where a connecting pipe should start/end.

        Unlike :meth:`tee_port_wc`, this shifts ``wc_center`` along
        ``pipe_axis`` — the pipe's **actual travel direction** — rather than
        the tee port axis stored in the JSON.

        This is the correct value to assign to ``wc_start`` / ``wc_end`` of
        the pipe component, because the pipe travels along its own axis, not
        necessarily along the tee port axis.  The two axes should agree for a
        well-formed tee, but when the router places a branch segment that
        immediately turns (or when the tee axis assignment is imprecise), they
        can differ, causing a visible gap or overlap in Blender.

        Parameters
        ----------
        tee:
            The tee_joint dict from the emitted JSON.
        port_id:
            The port identifier (e.g. ``"tee_01_branch"``).
        pipe_axis:
            The axis string of the connecting pipe (e.g. ``"+X"``).
        arriving:
            When ``True`` the pipe is *arriving* at this tee (i.e. the tee is
            the segment's ``to_port``).  The port face is on the side the pipe
            comes **from**, which is the direction *opposite* to the pipe's
            travel axis.  When ``False`` (default) the pipe is *departing*
            from the tee (``from_port``), so the port face is in the same
            direction as the pipe's travel axis.
        """
        wc_center = list(tee["wc_center"])  # type: ignore[list-item]
        offset = self.tee_offset_m(tee, port_id)

        # For an arriving pipe the port stub is behind the tee centre relative
        # to the pipe's travel direction, so we negate the axis.
        effective_axis = _opposite_axis(pipe_axis) if arriving else pipe_axis

        # Warn when the effective axis disagrees with the tee port axis — this
        # indicates either a routing anomaly or an axis-assignment bug.
        for port in tee.get("ports", []):  # type: ignore[union-attr]
            p = port  # type: Dict[str, object]
            if str(p.get("port_id")) == port_id:
                tee_axis = str(p["axis"])
                if tee_axis != effective_axis:
                    log.warning(
                        "Tee port %r axis %r disagrees with effective pipe axis %r "
                        "(pipe_axis=%r, arriving=%r). "
                        "Using effective pipe axis for wc endpoint.",
                        port_id, tee_axis, effective_axis, pipe_axis, arriving,
                    )
                break

        return VoxelGeometryMaps.shift_wc(wc_center, effective_axis, offset)

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
        """Trim the first/last pipe of a segment to the correct tee port face.

        The pipe's ``wc_start`` / ``wc_end`` is set by shifting the tee's
        ``wc_center`` along the **pipe's own travel axis** (``pipe["axis"]``),
        not along the tee port axis stored in the JSON.

        Sign convention
        ---------------
        * **Departing pipe** (``from_port`` is a tee): the pipe leaves the tee
          in its travel direction, so the port face is at
          ``wc_center + offset × pipe_axis``.  ``arriving=False`` (default).
        * **Arriving pipe** (``to_port`` is a tee): the pipe reaches the tee
          from the opposite side, so the port face is at
          ``wc_center - offset × pipe_axis`` (i.e. ``wc_center + offset ×
          opposite(pipe_axis)``).  ``arriving=True``.

        This is the key invariant: the pipe endpoint must lie on the pipe's
        own axis line through the tee centre.  Using the tee port axis instead
        causes a perpendicular offset whenever the branch pipe doesn't start
        in the same direction as the tee port axis (e.g. when the router
        routes the branch segment in a different direction than the tee stub).
        """
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
                pipe_axis = str(first.get("axis", ""))
                if pipe_axis:
                    # departing: port face is in the pipe's travel direction
                    first["wc_start"] = self.tee_port_wc_for_pipe(
                        tee, from_port, pipe_axis, arriving=False
                    )
                    self._update_pipe_length_m(first)

        if isinstance(to_port, str) and to_port.startswith("tee_"):
            tee_id = self.tee_id_from_port(to_port)
            tee = tee_map.get(tee_id or "")
            last = self.last_pipe(components)  # type: ignore[arg-type]
            if tee and last:
                pipe_axis = str(last.get("axis", ""))
                if pipe_axis:
                    # arriving: port face is opposite to the pipe's travel direction
                    last["wc_end"] = self.tee_port_wc_for_pipe(
                        tee, to_port, pipe_axis, arriving=True
                    )
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
