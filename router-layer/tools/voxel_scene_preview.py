"""
voxel_scene_preview.py
======================
Quick voxel-level preview for generation-layer JSON.

Dependencies:
    pip install numpy matplotlib

Example:
    python router-layer/tools/voxel_scene_preview.py --json router-layer/output/router_output_instrument_process_signal.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch


RGBA = tuple[float, float, float, float]

COLOR_TANK: RGBA = (0.18, 0.55, 0.95, 0.22)
COLOR_CUSTOM_MODULE: RGBA = (0.08, 0.78, 0.78, 0.28)
COLOR_INSTRUMENT: RGBA = (0.15, 0.78, 0.32, 0.58)
COLOR_PIPE: RGBA = (0.95, 0.68, 0.20, 0.35)
COLOR_SIGNAL_LINE: RGBA = (0.97, 0.28, 0.22, 0.68)
COLOR_ELBOW: RGBA = (0.56, 0.34, 0.82, 0.68)
COLOR_TEE: RGBA = (0.86, 0.86, 0.22, 0.88)

PRIORITY_TANK = 1
PRIORITY_CUSTOM_MODULE = 2
PRIORITY_PIPE = 3
PRIORITY_SIGNAL = 4
PRIORITY_INSTRUMENT = 5
PRIORITY_ELBOW = 6
PRIORITY_TEE = 7


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize generation JSON as colored voxels.")
    parser.add_argument("--json", required=True, help="Path to generation-layer JSON file.")
    parser.add_argument(
        "--title",
        default="Voxel Preview",
        help="Plot title.",
    )
    return parser.parse_args()


def _in_bounds(vc: tuple[int, int, int], dims: tuple[int, int, int]) -> bool:
    x, y, z = vc
    nx, ny, nz = dims
    return 0 <= x < nx and 0 <= y < ny and 0 <= z < nz


def _paint_voxel(
    vc: tuple[int, int, int],
    dims: tuple[int, int, int],
    filled: np.ndarray,
    colors: np.ndarray,
    priority: np.ndarray,
    color: RGBA,
    level: int,
) -> None:
    if not _in_bounds(vc, dims):
        return
    x, y, z = vc
    if level < priority[x, y, z]:
    #    print(f"[Warning] level < priority[x, y, z] at {vc}: {level} < {priority[x, y, z]}")
        return
    filled[x, y, z] = True
    colors[x, y, z] = color
    priority[x, y, z] = level


def _line_voxels(a: tuple[int, int, int], b: tuple[int, int, int]) -> Iterable[tuple[int, int, int]]:
    x0, y0, z0 = a
    x1, y1, z1 = b
    dx = np.sign(x1 - x0)
    dy = np.sign(y1 - y0)
    dz = np.sign(z1 - z0)
    n = max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    for i in range(n + 1):
        yield (x0 + int(dx * i), y0 + int(dy * i), z0 + int(dz * i))


def _to_vc_from_wc(
    wc: list[float],
    origin: tuple[float, float, float],
    voxel_size: float,
) -> tuple[int, int, int]:
    ox, oy, oz = origin
    vx = int(round((wc[0] - ox) / voxel_size - 0.5))
    vy = int(round((wc[1] - oy) / voxel_size - 0.5))
    vz = int(round((wc[2] - oz) / voxel_size - 0.5))
    return (vx, vy, vz)


def main() -> None:
    args = _parse_args()
    json_path = Path(args.json)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    voxel_grid = data["meta"]["voxel_grid"]
    dims = tuple(int(v) for v in voxel_grid["dimensions"])
    origin = tuple(float(v) for v in voxel_grid["origin_wc"])
    voxel_size = float(voxel_grid["voxel_size"])

    filled = np.zeros(dims, dtype=bool)
    colors = np.empty(dims, dtype=object)
    priority = np.zeros(dims, dtype=np.int16)

    # Tanks / custom modules: paint placeholder bounding boxes.
    for asset in data.get("assets", []):
        atype = str(asset.get("type", ""))
        if atype not in {"Tank", "CustomModule"}:
            continue
        origin_v = asset.get("voxel_origin")
        extent_v = asset.get("voxel_extent")
        if not (isinstance(origin_v, list) and isinstance(extent_v, list) and len(origin_v) == 3 and len(extent_v) == 3):
            continue
        ox, oy, oz = (int(origin_v[0]), int(origin_v[1]), int(origin_v[2]))
        ex, ey, ez = (int(extent_v[0]), int(extent_v[1]), int(extent_v[2]))
        color = COLOR_CUSTOM_MODULE if atype == "CustomModule" else COLOR_TANK
        level = PRIORITY_CUSTOM_MODULE if atype == "CustomModule" else PRIORITY_TANK
        for x in range(ox, ox + ex):
            for y in range(oy, oy + ey):
                for z in range(oz, oz + ez):
                    _paint_voxel((x, y, z), dims, filled, colors, priority, color, level)

    # Instruments: paint one voxel marker.
    for asset in data.get("assets", []):
        if asset.get("type") != "Instrument":
            continue
        vc = None
        ports = asset.get("ports", [])
        if ports and isinstance(ports[0], dict) and isinstance(ports[0].get("vc"), list):
            raw = ports[0]["vc"]
            vc = (int(raw[0]), int(raw[1]), int(raw[2]))
        elif isinstance(asset.get("wc_center"), list):
            vc = _to_vc_from_wc(asset["wc_center"], origin, voxel_size)
        if vc is not None:
            _paint_voxel(vc, dims, filled, colors, priority, COLOR_INSTRUMENT, PRIORITY_INSTRUMENT)

    # Segments/components: paint centerlines.
    for seg in data.get("segments", []):
        for comp in seg.get("components", []):
            ctype = str(comp.get("type", ""))
            if ctype in {"Pipe", "SignalLine"} and isinstance(comp.get("vc_start"), list) and isinstance(comp.get("vc_end"), list):
                a = tuple(int(v) for v in comp["vc_start"])
                b = tuple(int(v) for v in comp["vc_end"])
                color = COLOR_SIGNAL_LINE if ctype == "SignalLine" else COLOR_PIPE
                level = PRIORITY_SIGNAL if ctype == "SignalLine" else PRIORITY_PIPE
                for vc in _line_voxels(a, b):
                    _paint_voxel(vc, dims, filled, colors, priority, color, level)
            elif ctype == "Elbow" and isinstance(comp.get("vc_center"), list):
                vc = tuple(int(v) for v in comp["vc_center"])
                _paint_voxel(vc, dims, filled, colors, priority, COLOR_ELBOW, PRIORITY_ELBOW)

    tee_rendered = 0
    for tee in data.get("tee_joints", []):
        vc_center = tee.get("vc_center")
        if not (isinstance(vc_center, list) and len(vc_center) == 3):
            continue
        vc = (int(vc_center[0]), int(vc_center[1]), int(vc_center[2]))
        _paint_voxel(vc, dims, filled, colors, priority, COLOR_TEE, PRIORITY_TEE)
        tee_rendered += 1

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.voxels(filled, facecolors=colors, edgecolor=(0.1, 0.1, 0.1, 0.08))

    ax.set_title(args.title)
    ax.set_xlabel("X (voxel)")
    ax.set_ylabel("Y (voxel)")
    ax.set_zlabel("Z (voxel)")
    ax.set_box_aspect((dims[0], dims[1], dims[2]))

    legend_items = [
        Patch(facecolor=COLOR_TANK, edgecolor="none", label="Tank bbox"),
        Patch(facecolor=COLOR_CUSTOM_MODULE, edgecolor="none", label="CustomModule bbox"),
        Patch(facecolor=COLOR_INSTRUMENT, edgecolor="none", label="Instrument"),
        Patch(facecolor=COLOR_PIPE, edgecolor="none", label="Pipe"),
        Patch(facecolor=COLOR_SIGNAL_LINE, edgecolor="none", label="SignalLine"),
        Patch(facecolor=COLOR_ELBOW, edgecolor="none", label="Elbow center"),
        Patch(facecolor=COLOR_TEE, edgecolor="none", label="Tee center"),
    ]
    ax.legend(handles=legend_items, loc="upper left", frameon=True)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()

