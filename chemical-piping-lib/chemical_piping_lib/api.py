"""
api.py
======
Public entry point for the chemical-piping-lib.

This is the **only** module external callers should import from::

    from chemical_piping_lib.api import build_from_json, build_from_file, clear_scene

Or via the package shorthand::

    from chemical_piping_lib import build_from_json

All other modules are internal implementation details.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from chemical_piping_lib.scene.assembler import BuildReport, assemble

log = logging.getLogger(__name__)


def build_from_json(json_data: dict | str) -> BuildReport:
    """
    Build a Blender scene from a JSON data structure.

    Parameters
    ----------
    json_data:
        Either a pre-parsed ``dict`` or a raw JSON **string** conforming to
        the chemical-piping-lib v1.x protocol.

    Returns
    -------
    :class:`~scene.assembler.BuildReport` with build statistics, warnings,
    and errors.

    Example
    -------
    .. code-block:: python

        import sys, json
        sys.path.append('/path/to/chemical-piping-lib')

        from chemical_piping_lib import build_from_json

        with open('scene.json') as f:
            data = json.load(f)

        report = build_from_json(data)
        print(report)
    """
    if isinstance(json_data, str):
        try:
            json_data = json.loads(json_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"build_from_json: invalid JSON string: {exc}") from exc

    if not isinstance(json_data, dict):
        raise TypeError(
            f"build_from_json: expected dict or str, got {type(json_data).__name__}."
        )

    log.info("build_from_json: starting build.")
    return assemble(json_data)


def build_from_file(json_path: str | Path) -> BuildReport:
    """
    Read a JSON file and build the Blender scene.

    Parameters
    ----------
    json_path:
        Path to the ``.json`` file.

    Returns
    -------
    :class:`~scene.assembler.BuildReport`

    Example
    -------
    .. code-block:: python

        from chemical_piping_lib import build_from_file
        report = build_from_file('my_plant.json')
        print(report)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"build_from_file: {path} does not exist.")

    log.info("build_from_file: reading %s", path)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    return assemble(data)


def clear_scene() -> None:
    """
    Remove all objects and collections created by a previous
    :func:`build_from_json` call from the current Blender file.

    This searches for collections whose names start with
    ``"ChemicalPlant_"`` and removes them along with all contained
    objects.

    .. warning::
        This is irreversible.  Use with care in interactive sessions.
    """
    import bpy
    from chemical_piping_lib.utils.material_utils import clear_all_materials
    from chemical_piping_lib.scene.registry import PortRegistry

    PortRegistry.clear()
    clear_all_materials()

    prefix = "ChemicalPlant_"
    to_remove = [
        col for col in bpy.data.collections
        if col.name.startswith(prefix)
    ]

    for col in to_remove:
        # Remove all objects in the collection tree first.
        _remove_objects_in_collection(col)
        bpy.data.collections.remove(col)

    log.info("clear_scene: removed %d root collection(s).", len(to_remove))


def export_scene(
    output_path: str | Path,
    fmt: str = "blend",
) -> None:
    """
    Export the current Blender scene to a file.

    Parameters
    ----------
    output_path:
        Destination file path (extension is appended / overridden based
        on *fmt*).
    fmt:
        Export format.  Supported values: ``"blend"``, ``"fbx"``, ``"obj"``.

    Notes
    -----
    FBX and OBJ exports use ``bpy.ops`` and therefore require a valid
    window context.  They work in interactive Blender but may fail in
    headless mode for older Blender versions.
    """
    import bpy

    path = Path(output_path)
    fmt  = fmt.lower()

    if fmt == "blend":
        bpy.ops.wm.save_as_mainfile(filepath=str(path.with_suffix(".blend")))

    elif fmt == "fbx":
        bpy.ops.export_scene.fbx(
            filepath=str(path.with_suffix(".fbx")),
            use_selection=False,
            apply_scale_options='FBX_SCALE_NONE',
        )

    elif fmt == "obj":
        bpy.ops.wm.obj_export(
            filepath=str(path.with_suffix(".obj")),
            export_selected_objects=False,
        )

    else:
        raise ValueError(f"export_scene: unsupported format {fmt!r}.")

    log.info("export_scene: exported to %s", path)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _remove_objects_in_collection(col) -> None:
    """Recursively remove all objects from a collection tree."""
    import bpy
    for child in list(col.children):
        _remove_objects_in_collection(child)
    for obj in list(col.objects):
        mesh = obj.data if obj.type == 'MESH' else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
