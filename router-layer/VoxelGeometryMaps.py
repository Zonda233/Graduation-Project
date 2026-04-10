from __future__ import annotations

from typing import ClassVar, Dict, List, Tuple

from .config import RouterConfig

Vc = Tuple[int, int, int]


class VoxelGeometryMaps:
    """Static axis / DN lookup tables and voxel↔world helpers for pipeline JSON emission."""

    AXIS_BY_DELTA: ClassVar[Dict[Tuple[int, int, int], str]] = {
        (1, 0, 0): "+X",
        (-1, 0, 0): "-X",
        (0, 1, 0): "+Y",
        (0, -1, 0): "-Y",
        (0, 0, 1): "+Z",
        (0, 0, -1): "-Z",
    }
    VEC_BY_AXIS: ClassVar[Dict[str, Tuple[float, float, float]]] = {
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    OD_BY_NOMINAL_M: ClassVar[Dict[float, float]] = {
        0.015: 0.02134,
        0.020: 0.02667,
        0.025: 0.03340,
        0.032: 0.04216,
        0.040: 0.04826,
        0.050: 0.06033,
        0.065: 0.07315,
        0.080: 0.08890,
        0.100: 0.11430,
        0.125: 0.14130,
        0.150: 0.16830,
        0.200: 0.21910,
        0.250: 0.27305,
        0.300: 0.32385,
        0.350: 0.35560,
        0.400: 0.40640,
        0.450: 0.45720,
        0.500: 0.50800,
    }

    @staticmethod
    def delta_vc(a: Vc, b: Vc) -> Vc:
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    @staticmethod
    def vc_to_wc(vc: Vc, config: RouterConfig) -> List[float]:
        ox, oy, oz = config.origin_wc
        vs = config.voxel_size
        return [
            ox + (vc[0] + 0.5) * vs,
            oy + (vc[1] + 0.5) * vs,
            oz + (vc[2] + 0.5) * vs,
        ]

    @classmethod
    def outer_diameter_m(cls, nominal_diameter_m: float) -> float:
        best_nominal = min(cls.OD_BY_NOMINAL_M.keys(), key=lambda x: abs(x - nominal_diameter_m))
        return cls.OD_BY_NOMINAL_M[best_nominal]

    @classmethod
    def shift_wc(cls, wc: List[float], axis: str, distance_m: float) -> List[float]:
        vec = cls.VEC_BY_AXIS[axis]
        return [
            wc[0] + vec[0] * distance_m,
            wc[1] + vec[1] * distance_m,
            wc[2] + vec[2] * distance_m,
        ]

    @staticmethod
    def pipe_length_m(wc_start: List[float], wc_end: List[float]) -> float:
        dx = wc_end[0] - wc_start[0]
        dy = wc_end[1] - wc_start[1]
        dz = wc_end[2] - wc_start[2]
        return (dx * dx + dy * dy + dz * dz) ** 0.5
