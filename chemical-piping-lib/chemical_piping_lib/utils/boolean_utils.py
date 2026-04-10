"""
boolean_utils.py
================
Boolean modifier helpers for the chemical-piping-lib.

All boolean operations in the library are routed through this module so
that solver selection, fallback logic, and error handling live in one place.

Blender 4.5 introduces the ``MANIFOLD`` solver which is both fast and
reliable for water-tight (manifold) meshes — see the ``BooleanModifier``
API docs.  We use it as the default and fall back gracefully when it fails.

Fallback chain
--------------
::

    MANIFOLD solver
        ↓ fails
    EXACT solver
        ↓ fails
    Visual join  (bpy.ops.object.join — geometry overlaps, no boolean hole)
        → WARNING logged; asset is flagged as approximate

Mesh manifold requirement
-------------------------
The MANIFOLD solver requires both operands to be manifold (every edge
shared by exactly two faces, no boundary edges, consistent winding).  We
check this with :func:`bmesh_utils.check_manifold_obj` before every
boolean and log a detailed warning if the check fails, so developers can
spot topology issues early during the build.
"""

from __future__ import annotations

import logging

import bpy

from chemical_piping_lib.config import BOOLEAN_THRESHOLD, RUNTIME
from chemical_piping_lib.utils import bmesh_utils, ops_wrapper

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_boolean(
    base_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
    operation: str,      # 'UNION' | 'DIFFERENCE' | 'INTERSECT'
    solver: str,         # 'MANIFOLD' | 'EXACT' | 'FLOAT'
) -> bool:
    """
    Add a boolean modifier to *base_obj*, apply it, and return success.

    The modifier is cleaned up regardless of success so that the object
    is left in a consistent state.
    """
    mod_name = f"_cpl_bool_{operation.lower()}"

    mod = base_obj.modifiers.new(name=mod_name, type='BOOLEAN')
    mod.operation  = operation
    mod.solver     = solver
    mod.object     = cutter_obj
    mod.double_threshold = BOOLEAN_THRESHOLD

    success = ops_wrapper.apply_modifier(base_obj, mod_name)

    # If apply failed the modifier may still be on the stack; remove it.
    if mod_name in base_obj.modifiers:
        base_obj.modifiers.remove(base_obj.modifiers[mod_name])

    return success


def _pre_check(obj: bpy.types.Object, label: str) -> bool:
    """
    Log a warning if *obj* is not manifold.  Returns the manifold status.
    """
    ok = bmesh_utils.check_manifold_obj(obj)
    if not ok:
        log.warning(
            "boolean_utils: %s (%r) is not manifold. "
            "Boolean result may be incorrect.  "
            "Check for open edges, duplicate vertices, or flipped normals.",
            label, obj.name,
        )
    return ok


# ---------------------------------------------------------------------------
# Public boolean operations
# ---------------------------------------------------------------------------

def boolean_union(
    base_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
    keep_cutter: bool = False,
) -> bool:
    """
    Perform a **union** boolean on *base_obj* with *cutter_obj*.

    Parameters
    ----------
    base_obj:    The object that receives the modifier and survives.
    cutter_obj:  The object used as the boolean operand.
    keep_cutter: If ``False`` (default), *cutter_obj* is deleted after the
                 operation regardless of success.

    Returns
    -------
    ``True`` if the boolean was applied successfully (with any solver).
    ``False`` if all solvers failed and a visual join was used as fallback.
    """
    return _boolean_op(base_obj, cutter_obj, 'UNION', keep_cutter)


def boolean_difference(
    base_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
    keep_cutter: bool = False,
) -> bool:
    """
    Perform a **difference** boolean on *base_obj* subtracting *cutter_obj*.

    Parameters and return value are the same as :func:`boolean_union`.
    """
    return _boolean_op(base_obj, cutter_obj, 'DIFFERENCE', keep_cutter)


def boolean_intersect(
    base_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
    keep_cutter: bool = False,
) -> bool:
    """
    Perform an **intersect** boolean on *base_obj* with *cutter_obj*.
    """
    return _boolean_op(base_obj, cutter_obj, 'INTERSECT', keep_cutter)


# ---------------------------------------------------------------------------
# Core dispatcher
# ---------------------------------------------------------------------------

def _boolean_op(
    base_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
    operation: str,
    keep_cutter: bool,
) -> bool:
    """
    Internal dispatcher: try solvers in priority order, fall back to visual
    join, clean up cutter.
    """
    # Pre-flight manifold check (warnings only, non-blocking).
    _pre_check(base_obj,   "base_obj")
    _pre_check(cutter_obj, "cutter_obj")

    # Solver priority list.
    preferred = RUNTIME.boolean_solver          # e.g. 'MANIFOLD'
    solvers = _solver_priority(preferred)

    success = False
    for solver in solvers:
        log.debug(
            "_boolean_op: trying %s %s on %r with solver %s.",
            operation, cutter_obj.name, base_obj.name, solver,
        )
        if _apply_boolean(base_obj, cutter_obj, operation, solver):
            log.debug("_boolean_op: success with solver %s.", solver)
            success = True
            break
        else:
            log.warning(
                "_boolean_op: solver %s failed for %s on %r.  Trying next solver.",
                solver, operation, base_obj.name,
            )

    if not success:
        # Last resort: visual join (only meaningful for UNION-like intent).
        log.warning(
            "_boolean_op: ALL solvers failed for %s on %r.  "
            "Falling back to visual join (geometry will overlap).",
            operation, base_obj.name,
        )
        if operation == 'UNION':
            ops_wrapper.join_objects(base_obj, [cutter_obj])
            # cutter_obj is consumed by join; no need to delete separately.
            return False
        # For DIFFERENCE / INTERSECT there is no sensible visual fallback;
        # leave base_obj unchanged and log a prominent error.
        log.error(
            "_boolean_op: no fallback available for %s; %r is unchanged.",
            operation, base_obj.name,
        )

    # Clean up cutter unless caller wants to keep it.
    if not keep_cutter:
        # join_objects already consumed the cutter for UNION fallback.
        try:
            ops_wrapper.delete_object(cutter_obj)
        except Exception:   # cutter may already be gone after join
            pass

    return success


def _solver_priority(preferred: str) -> list[str]:
    """
    Return the ordered list of solvers to try, starting with *preferred*.

    'MANIFOLD' → ['MANIFOLD', 'EXACT']
    'EXACT'    → ['EXACT', 'MANIFOLD']
    'FLOAT'    → ['FLOAT', 'EXACT', 'MANIFOLD']
    """
    all_solvers = ['MANIFOLD', 'EXACT', 'FLOAT']
    ordered = [preferred] + [s for s in all_solvers if s != preferred]
    return ordered
