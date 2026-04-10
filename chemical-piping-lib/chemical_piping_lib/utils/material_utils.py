"""
material_utils.py
=================
Material creation, retrieval, and caching for the chemical-piping-lib.

All Blender materials used by the library are created through this module.
A simple name-based cache ensures that each logical material is created
only once per Blender session, even if many objects share it.

Material naming convention
--------------------------
Every material created here is prefixed with ``"CPL_"`` (Chemical Piping
Lib) to distinguish it from any user-created materials and to allow easy
batch-deletion via :func:`clear_all_materials`.
"""

from __future__ import annotations

import logging

import bpy

from chemical_piping_lib.config import MATERIAL_PRESETS

log = logging.getLogger(__name__)

_PREFIX = "CPL_"


# ---------------------------------------------------------------------------
# Internal cache  {material_id -> bpy.types.Material}
# ---------------------------------------------------------------------------
_cache: dict[str, bpy.types.Material] = {}


def _make_principled_material(
    name: str,
    base_color: tuple[float, float, float, float],
    metallic: float,
    roughness: float,
) -> bpy.types.Material:
    """
    Create a new Blender material with a single Principled BSDF node.

    The material uses nodes and has its viewport colour set to match
    the base colour for quick visual feedback.
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    nodes.clear()

    # Output node.
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)

    # Principled BSDF.
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)

    # Set Principled BSDF inputs.
    bsdf.inputs["Base Color"].default_value  = base_color
    bsdf.inputs["Metallic"].default_value    = metallic
    bsdf.inputs["Roughness"].default_value   = roughness

    # Link BSDF to output.
    mat.node_tree.links.new(
        bsdf.outputs["BSDF"],
        output.inputs["Surface"],
    )

    # Viewport colour (diffuse colour).
    mat.diffuse_color = base_color

    return mat


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_or_create(material_id: str) -> bpy.types.Material:
    """
    Return the Blender material for *material_id*, creating it if necessary.

    Look-up order
    -------------
    1. In-process cache ``_cache``.
    2. Existing Blender material data-block whose name is ``CPL_{material_id}``.
    3. Preset from :data:`config.MATERIAL_PRESETS`.
    4. If *material_id* is not in the presets, the ``"default"`` preset is
       used and a warning is logged.

    Parameters
    ----------
    material_id:
        Key used in :data:`config.MATERIAL_PRESETS`, e.g.
        ``"carbon_steel"``, ``"stainless_steel"``.
        Also accepts the ``mat_*`` ids from the JSON ``materials`` block
        after they have been registered via :func:`register_from_json`.

    Returns
    -------
    A ``bpy.types.Material`` with nodes configured.
    """
    if material_id in _cache:
        return _cache[material_id]

    blender_name = _PREFIX + material_id

    # Check if a matching datablock already exists (e.g. from a previous run
    # in the same Blender session).
    existing = bpy.data.materials.get(blender_name)
    if existing is not None:
        _cache[material_id] = existing
        return existing

    # Resolve preset.
    preset = MATERIAL_PRESETS.get(material_id)
    if preset is None:
        log.warning(
            "material_utils: unknown material_id %r; using 'default' preset.",
            material_id,
        )
        preset = MATERIAL_PRESETS["default"]

    mat = _make_principled_material(
        name=blender_name,
        base_color=tuple(preset["base_color"]),  # type: ignore[arg-type]
        metallic=float(preset["metallic"]),
        roughness=float(preset["roughness"]),
    )

    _cache[material_id] = mat
    log.debug("material_utils: created material %r.", blender_name)
    return mat


def register_from_json(materials_block: list[dict]) -> None:
    """
    Pre-create materials defined in the JSON ``materials`` array.

    Each entry may define its own ``visual`` overrides.  If ``visual`` is
    absent the library falls back to the nearest preset.

    Parameters
    ----------
    materials_block:
        The ``json_data["materials"]`` list from the input JSON.
    """
    for entry in materials_block:
        mid  = entry.get("id", "")
        if not mid:
            log.warning("register_from_json: entry missing 'id' field: %s", entry)
            continue

        visual = entry.get("visual")
        if visual:
            # Override the preset table for this session with JSON-specified values.
            from chemical_piping_lib.config import MATERIAL_PRESETS  # local to avoid circular
            MATERIAL_PRESETS[mid] = {
                "base_color": tuple(visual["base_color"]),
                "metallic":   float(visual.get("metallic", 0.5)),
                "roughness":  float(visual.get("roughness", 0.5)),
            }

        # Actually create the material now (warms the cache).
        get_or_create(mid)


def assign_material(obj: bpy.types.Object, material_id: str) -> None:
    """
    Assign the material for *material_id* to *obj*.

    If the object already has a material in slot 0 it is replaced;
    otherwise a new slot is appended.

    Parameters
    ----------
    obj:         Target Blender object (must have a Mesh data-block).
    material_id: Material identifier (same key as :func:`get_or_create`).
    """
    mat = get_or_create(material_id)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def clear_cache() -> None:
    """
    Flush the in-process material cache.

    Call this at the start of each ``build_from_json`` invocation so that
    stale references from a previous build do not interfere.
    """
    _cache.clear()


def clear_all_materials() -> None:
    """
    Remove all ``CPL_*`` materials from the current Blender file.

    Useful for resetting the scene between test runs.
    """
    clear_cache()
    to_remove = [m for m in bpy.data.materials if m.name.startswith(_PREFIX)]
    for mat in to_remove:
        bpy.data.materials.remove(mat)
    log.debug("clear_all_materials: removed %d material(s).", len(to_remove))
