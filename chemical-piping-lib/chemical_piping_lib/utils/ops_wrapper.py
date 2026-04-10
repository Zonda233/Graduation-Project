"""
ops_wrapper.py
==============
Safe wrappers around ``bpy.ops.*`` calls for Blender 4.x.

Motivation
----------
In Blender 4.x ``bpy.ops`` operators require a valid context (window,
screen, area, region, active object, etc.).  In *headless* mode
(``blender --background``) many of these are ``None``, which causes
``RuntimeError: Operator bpy.ops.object.modifier_apply.poll() failed``.

The wrappers here use ``bpy.context.temp_override(...)`` (the Blender 4.x
replacement for the deprecated dict-override pattern) to supply the minimum
necessary context.  They also implement a structured fallback so that a
failed modifier apply never crashes the entire build pipeline.

Architectural rule
------------------
This is the **only** module in the library that is allowed to call
``bpy.ops.*``.  All other modules must go through these wrappers.
"""

from __future__ import annotations

import logging

import bpy

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_object_in_scene(obj: bpy.types.Object) -> None:
    """
    Make sure *obj* is linked to the current scene collection.

    Some operations fail if the object exists in ``bpy.data`` but is not
    part of any scene.
    """
    scene_col = bpy.context.scene.collection
    # Walk all collections in the scene and check for the object.
    all_objects = set(bpy.context.scene.objects)
    if obj not in all_objects:
        scene_col.objects.link(obj)
        log.debug("_ensure_object_in_scene: linked %r to scene collection.", obj.name)


def _make_override(obj: bpy.types.Object) -> dict:
    """
    Build the minimum context-override dict needed for object-mode operators
    that act on a single active object.

    In Blender 4.x ``temp_override`` accepts keyword arguments, not a dict,
    but we build a dict here for clarity and unpack it at the call site.
    """
    return dict(
        active_object=obj,
        object=obj,
        selected_objects=[obj],
        selected_editable_objects=[obj],
        # mode is an enum string, not set via the override dict in 4.x;
        # object mode is assumed (the objects we build are never in edit mode).
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_modifier(obj: bpy.types.Object, modifier_name: str) -> bool:
    """
    Apply a named modifier to *obj* and return whether the operation
    succeeded.

    Strategy
    --------
    1. Ensure the object is in the current scene.
    2. Use ``bpy.context.temp_override`` to supply the active-object context.
    3. Call ``bpy.ops.object.modifier_apply``.
    4. On ``RuntimeError`` log a warning and return ``False``.

    Parameters
    ----------
    obj:           The object whose modifier should be applied.
    modifier_name: The ``.name`` attribute of the modifier to apply.

    Returns
    -------
    ``True`` if the modifier was applied successfully, ``False`` otherwise.
    """
    _ensure_object_in_scene(obj)

    if modifier_name not in obj.modifiers:
        log.warning(
            "apply_modifier: modifier %r not found on object %r.",
            modifier_name, obj.name,
        )
        return False

    try:
        with bpy.context.temp_override(**_make_override(obj)):
            bpy.ops.object.modifier_apply(modifier=modifier_name)
        log.debug(
            "apply_modifier: applied %r on %r.", modifier_name, obj.name
        )
        return True

    except RuntimeError as exc:
        log.warning(
            "apply_modifier: failed to apply %r on %r: %s",
            modifier_name, obj.name, exc,
        )
        return False


def delete_object(obj: bpy.types.Object) -> None:
    """
    Safely remove *obj* from the scene and purge its mesh data-block.

    After this call the Python reference *obj* is invalid; do not use it.

    Parameters
    ----------
    obj: The object to delete.  If it is not in the scene, it is still
         purged from ``bpy.data``.
    """
    name = obj.name  # capture before deletion
    mesh = obj.data if obj.type == 'MESH' else None

    # Unlink from all collections.
    for col in list(obj.users_collection):
        col.objects.unlink(obj)

    # Remove the object data-block.
    bpy.data.objects.remove(obj, do_unlink=True)

    # Remove the mesh data-block if it is now orphaned.
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)

    log.debug("delete_object: removed %r.", name)


def join_objects(
    base_obj: bpy.types.Object,
    others: list[bpy.types.Object],
) -> bpy.types.Object:
    """
    Join *others* into *base_obj* (equivalent to Ctrl+J in the UI).

    All objects in *others* are consumed; only *base_obj* remains.
    Returns *base_obj* for convenience.

    Parameters
    ----------
    base_obj: The object that will survive the join.
    others:   Objects to be merged into *base_obj*.  May be empty (no-op).

    Returns
    -------
    *base_obj* (now containing the merged geometry).
    """
    if not others:
        return base_obj

    for o in others:
        _ensure_object_in_scene(o)
    _ensure_object_in_scene(base_obj)

    all_objs = [base_obj] + list(others)

    try:
        with bpy.context.temp_override(
            active_object=base_obj,
            object=base_obj,
            selected_objects=all_objs,
            selected_editable_objects=all_objs,
        ):
            bpy.ops.object.join()
        log.debug(
            "join_objects: joined %d objects into %r.",
            len(others), base_obj.name,
        )
    except RuntimeError as exc:
        log.warning("join_objects: failed: %s", exc)

    return base_obj
