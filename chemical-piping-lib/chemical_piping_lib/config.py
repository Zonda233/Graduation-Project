"""
config.py
=========
Single source of truth for all global constants, lookup tables, and
runtime-mutable settings used across the library.

Design rule
-----------
This module has **zero imports** from other library modules.  Every other
module may import from here, but this module never imports from siblings.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Blender mathutils is available at runtime inside Blender's Python.
# We do NOT import it at the top level so that unit-tests running outside
# Blender can still import config.py safely.  Consumers that need Vector
# objects should import mathutils themselves.
# ---------------------------------------------------------------------------

# ===========================================================================
# 1.  Voxel grid
# ===========================================================================

#: Edge length of one voxel cell in metres.
VOXEL_SIZE: float = 0.2

#: World-space origin that corresponds to voxel coordinate (0, 0, 0).
#: Expressed as a plain tuple so this file stays free of mathutils.
ORIGIN_WC: tuple[float, float, float] = (0.0, 0.0, 0.0)

#: Number of voxel cells along each axis  (X, Y, Z).
GRID_DIMENSIONS: tuple[int, int, int] = (20, 20, 20)


# ===========================================================================
# 2.  Mesh quality / geometry resolution
# ===========================================================================

#: Circumferential segments for pipes and tank shells.
MESH_SEGMENTS: int = 32

#: Number of cross-sections along the arc of an elbow (higher = smoother).
ELBOW_ARC_SEGMENTS: int = 16

#: Enable hollow pipes (tube with wall thickness).  Set False for solid
#: cylinders, which are cheaper and fine for a voxel-style overview.
PIPE_HOLLOW: bool = False

#: Show bolt holes on flanges.  Expensive (many boolean ops), off by default.
FLANGE_SHOW_BOLTS: bool = False

#: Short stub (metres) extruded from a tank nozzle beyond the shell surface.
NOZZLE_LENGTH: float = 0.05


# ===========================================================================
# 3.  Boolean operations
# ===========================================================================

#: Preferred boolean solver.  'MANIFOLD' is new in Blender 4.5 and is the
#: fastest solver that still produces clean results on manifold meshes.
#: Fallback order: MANIFOLD → EXACT → visual-join (no boolean).
BOOLEAN_SOLVER: str = "MANIFOLD"

#: Co-planarity / overlap tolerance fed to the boolean modifier.
BOOLEAN_THRESHOLD: float = 1e-6


# ===========================================================================
# 4.  Axis → direction string enumeration
# ===========================================================================

#: All valid axis direction strings accepted by the JSON protocol.
VALID_AXES: tuple[str, ...] = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")

#: Opposite direction for each axis string.
AXIS_OPPOSITE: dict[str, str] = {
    "+X": "-X", "-X": "+X",
    "+Y": "-Y", "-Y": "+Y",
    "+Z": "-Z", "-Z": "+Z",
}


# ===========================================================================
# 5.  DN (nominal diameter) pipe specifications
#     All dimensions in metres.
#     Outer diameters follow ISO 4200 / GB/T 17395.
#     Wall thicknesses are Schedule 40 (ASME B36.10M) equivalents.
# ===========================================================================

#: Maps DN label (e.g. "DN50") to pipe geometry parameters.
DN_TABLE: dict[str, dict[str, float]] = {
    "DN15":  {"outer_diameter": 0.02134, "wall_thickness": 0.00277},
    "DN20":  {"outer_diameter": 0.02667, "wall_thickness": 0.00277},
    "DN25":  {"outer_diameter": 0.03340, "wall_thickness": 0.00338},
    "DN32":  {"outer_diameter": 0.04216, "wall_thickness": 0.00338},
    "DN40":  {"outer_diameter": 0.04826, "wall_thickness": 0.00368},
    "DN50":  {"outer_diameter": 0.06033, "wall_thickness": 0.00368},
    "DN65":  {"outer_diameter": 0.07315, "wall_thickness": 0.00505},
    "DN80":  {"outer_diameter": 0.08890, "wall_thickness": 0.00505},
    "DN100": {"outer_diameter": 0.11430, "wall_thickness": 0.00600},
    "DN125": {"outer_diameter": 0.14130, "wall_thickness": 0.00635},
    "DN150": {"outer_diameter": 0.16830, "wall_thickness": 0.00711},
    "DN200": {"outer_diameter": 0.21910, "wall_thickness": 0.00813},
    "DN250": {"outer_diameter": 0.27305, "wall_thickness": 0.00953},
    "DN300": {"outer_diameter": 0.32385, "wall_thickness": 0.01016},
    "DN350": {"outer_diameter": 0.35560, "wall_thickness": 0.01111},
    "DN400": {"outer_diameter": 0.40640, "wall_thickness": 0.01270},
    "DN450": {"outer_diameter": 0.45720, "wall_thickness": 0.01270},
    "DN500": {"outer_diameter": 0.50800, "wall_thickness": 0.01270},
}


def get_dn_spec(nominal_diameter_m: float) -> dict[str, float]:
    """
    Look up DN pipe specification from a nominal diameter expressed in metres.

    The function finds the closest DN entry whose nominal diameter is within
    a reasonable tolerance (±20 %) of the requested value.

    Parameters
    ----------
    nominal_diameter_m:
        Nominal pipe diameter in metres, e.g. ``0.1`` for DN100.

    Returns
    -------
    dict with keys ``outer_diameter`` and ``wall_thickness`` (both in metres).

    Raises
    ------
    ValueError
        If no matching DN size can be found.

    Examples
    --------
    >>> spec = get_dn_spec(0.1)
    >>> spec["outer_diameter"]
    0.1143
    """
    # Build a mapping: approximate nominal diameter → DN label.
    # Nominal diameter ≈ outer_diameter for most DN sizes, but not exactly;
    # we use the numeric portion of the DN label as the authoritative nominal.
    best_key: str | None = None
    best_diff: float = float("inf")

    for dn_label in DN_TABLE:
        dn_mm = int(dn_label[2:])          # e.g. "DN100" → 100
        dn_m  = dn_mm / 1000.0             # 100 → 0.1
        diff  = abs(dn_m - nominal_diameter_m)
        if diff < best_diff:
            best_diff = diff
            best_key  = dn_label

    # Reject if the closest match is more than 20 % away.
    if best_key is None or best_diff > nominal_diameter_m * 0.20:
        raise ValueError(
            f"No DN specification found for nominal diameter "
            f"{nominal_diameter_m} m (closest: {best_key}, diff={best_diff:.4f} m).  "
            f"Check the DN_TABLE in config.py."
        )

    return DN_TABLE[best_key]


# ===========================================================================
# 6.  Flange specifications (simplified, PN16 series)
#     Dimensions follow GB/T 9119 / EN 1092-1.
# ===========================================================================

#: Maps DN label to flange geometry.
#: ``outer_diameter``: flange OD in metres.
#: ``thickness``     : flange body thickness in metres.
#: ``bolt_count``    : number of bolt holes.
#: ``bolt_circle_d`` : bolt-hole pitch-circle diameter in metres.
#: ``bolt_hole_d``   : individual bolt-hole diameter in metres.
FLANGE_TABLE: dict[str, dict[str, float | int]] = {
    "DN25":  {"outer_diameter": 0.115, "thickness": 0.018, "bolt_count": 4,  "bolt_circle_d": 0.085, "bolt_hole_d": 0.014},
    "DN50":  {"outer_diameter": 0.165, "thickness": 0.020, "bolt_count": 4,  "bolt_circle_d": 0.125, "bolt_hole_d": 0.018},
    "DN80":  {"outer_diameter": 0.200, "thickness": 0.022, "bolt_count": 8,  "bolt_circle_d": 0.160, "bolt_hole_d": 0.018},
    "DN100": {"outer_diameter": 0.220, "thickness": 0.022, "bolt_count": 8,  "bolt_circle_d": 0.180, "bolt_hole_d": 0.018},
    "DN150": {"outer_diameter": 0.285, "thickness": 0.024, "bolt_count": 8,  "bolt_circle_d": 0.240, "bolt_hole_d": 0.022},
    "DN200": {"outer_diameter": 0.340, "thickness": 0.026, "bolt_count": 12, "bolt_circle_d": 0.295, "bolt_hole_d": 0.022},
    "DN250": {"outer_diameter": 0.395, "thickness": 0.029, "bolt_count": 12, "bolt_circle_d": 0.350, "bolt_hole_d": 0.026},
    "DN300": {"outer_diameter": 0.445, "thickness": 0.032, "bolt_count": 12, "bolt_circle_d": 0.400, "bolt_hole_d": 0.026},
}


def get_flange_spec(nominal_diameter_m: float) -> dict[str, float | int]:
    """
    Same nearest-match logic as :func:`get_dn_spec`, but for flanges.
    """
    best_key: str | None = None
    best_diff: float = float("inf")

    for dn_label in FLANGE_TABLE:
        dn_m = int(dn_label[2:]) / 1000.0
        diff = abs(dn_m - nominal_diameter_m)
        if diff < best_diff:
            best_diff = diff
            best_key  = dn_label

    if best_key is None:
        raise ValueError(
            f"No flange specification found for nominal diameter {nominal_diameter_m} m."
        )

    return FLANGE_TABLE[best_key]


# ===========================================================================
# 7.  Material visual presets
#     Values map directly to Blender Principled BSDF inputs.
# ===========================================================================

#: Each entry: base_color (RGBA), metallic (0–1), roughness (0–1).
MATERIAL_PRESETS: dict[str, dict] = {
    "carbon_steel": {
        "base_color": (0.40, 0.40, 0.45, 1.0),
        "metallic":   0.9,
        "roughness":  0.4,
    },
    "stainless_steel": {
        "base_color": (0.70, 0.70, 0.75, 1.0),
        "metallic":   1.0,
        "roughness":  0.2,
    },
    "valve_body": {
        "base_color": (0.80, 0.30, 0.10, 1.0),
        "metallic":   0.7,
        "roughness":  0.5,
    },
    "tank_shell": {
        "base_color": (0.60, 0.62, 0.65, 1.0),
        "metallic":   0.85,
        "roughness":  0.3,
    },
    "flange": {
        "base_color": (0.35, 0.35, 0.38, 1.0),
        "metallic":   0.9,
        "roughness":  0.45,
    },
    # Fallback used when a material_id in the JSON is unrecognised.
    "default": {
        "base_color": (0.50, 0.50, 0.50, 1.0),
        "metallic":   0.5,
        "roughness":  0.5,
    },
}


# ===========================================================================
# 8.  Runtime-mutable scene settings
#     Populated by scene/assembler.py when it reads the JSON "meta" block.
#     All other modules read from here instead of from the JSON directly.
# ===========================================================================

class _RuntimeSettings:
    """
    Mutable container for per-build settings that override the defaults above.
    Assembler writes here once; asset classes read from here.
    """
    voxel_size: float                           = VOXEL_SIZE
    origin_wc:  tuple[float, float, float]      = ORIGIN_WC
    grid_dimensions: tuple[int, int, int]       = GRID_DIMENSIONS
    mesh_segments: int                          = MESH_SEGMENTS
    elbow_arc_segments: int                     = ELBOW_ARC_SEGMENTS
    boolean_solver: str                         = BOOLEAN_SOLVER

    def reset(self) -> None:
        """Restore all fields to module-level defaults."""
        self.voxel_size        = VOXEL_SIZE
        self.origin_wc         = ORIGIN_WC
        self.grid_dimensions   = GRID_DIMENSIONS
        self.mesh_segments     = MESH_SEGMENTS
        self.elbow_arc_segments = ELBOW_ARC_SEGMENTS
        self.boolean_solver    = BOOLEAN_SOLVER

    def apply_meta(self, meta: dict) -> None:
        """
        Override settings from the JSON ``meta`` block.

        Only known keys are applied; unknown keys are silently ignored so that
        future JSON versions do not break older library versions.
        """
        vg = meta.get("voxel_grid", {})
        if "voxel_size" in vg:
            self.voxel_size = float(vg["voxel_size"])
        if "origin_wc" in vg:
            self.origin_wc = tuple(float(v) for v in vg["origin_wc"])  # type: ignore[assignment]
        if "dimensions" in vg:
            self.grid_dimensions = tuple(int(v) for v in vg["dimensions"])  # type: ignore[assignment]


#: Global singleton.  Import and read/write this object everywhere.
RUNTIME = _RuntimeSettings()
