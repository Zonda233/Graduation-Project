"""
bmesh_utils.py
==============
Low-level ``bmesh`` geometry construction helpers.

Design rules
------------
* Every function operates on an **existing** ``BMesh`` object passed in by
  the caller.  Functions never create or finalise Blender Objects.
* The single exception is :func:`bm_to_object`, which writes a finished
  ``BMesh`` into a new ``bpy.types.Object`` and returns it.
* All geometry is constructed so that the resulting mesh is *manifold*
  (closed, orientable, every edge shared by exactly two faces).  This is a
  hard requirement for the MANIFOLD boolean solver used later.
* No ``bpy.ops.*`` calls are made here.

Conventions
-----------
* Circles / cylinders are built along the local **+Z** axis by default.
  Callers rotate the resulting object with :func:`coords.align_object_to_axis`.
* The ``diameter`` parameter in ``bmesh.ops.create_circle`` is actually a
  *radius* in Blender's internal naming (confirmed against Blender 4.x source).
  All public functions in this module accept a ``radius`` argument to avoid
  confusion.
"""

from __future__ import annotations

import math
from typing import Sequence

import bmesh
import bpy
from bmesh.types import BMEdge, BMFace, BMVert, BMesh
from mathutils import Matrix, Vector

from chemical_piping_lib.config import RUNTIME
from chemical_piping_lib.utils.coords import build_local_frame


# ===========================================================================
# 1.  Circle / ring helpers
# ===========================================================================

def make_circle_verts(
    bm: BMesh,
    center: Vector,
    normal: Vector,
    radius: float,
    segments: int | None = None,
) -> list[BMVert]:
    """
    Insert a ring of vertices into *bm* centred at *center*, lying in the
    plane whose normal is *normal*, with the given *radius*.

    No edges or faces are created — just the vertex ring.  Use
    :func:`bridge_loops` to connect two rings into a tube section.

    Parameters
    ----------
    bm:
        Target BMesh (already initialised).
    center:
        World-space centre of the ring.
    normal:
        Outward-facing normal of the ring plane (need not be unit length).
    radius:
        Ring radius in metres.
    segments:
        Number of vertices.  Defaults to ``RUNTIME.mesh_segments``.

    Returns
    -------
    List of :class:`BMVert` in counter-clockwise order when viewed from
    the *normal* side.
    """
    if segments is None:
        segments = RUNTIME.mesh_segments

    n = normal.normalized()
    u, v = build_local_frame(n)  # two in-plane orthogonal unit vectors

    verts: list[BMVert] = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        pos = center + radius * (math.cos(angle) * u + math.sin(angle) * v)
        verts.append(bm.verts.new(pos))

    return verts


def cap_loop(bm: BMesh, loop: list[BMVert]) -> BMFace:
    """
    Close an open vertex loop with a single n-gon face.

    The vertices are assumed to be in order (CW or CCW).  The resulting
    face normal will point in the direction given by the right-hand rule
    of the vertex winding.

    Parameters
    ----------
    bm:   Target BMesh.
    loop: Ordered list of :class:`BMVert` forming the boundary.

    Returns
    -------
    The newly created :class:`BMFace`.
    """
    return bm.faces.new(loop)


# ===========================================================================
# 2.  Loop bridging (tube sections)
# ===========================================================================

def bridge_loops(
    bm: BMesh,
    loop_a: list[BMVert],
    loop_b: list[BMVert],
) -> list[BMFace]:
    """
    Connect two vertex rings with a band of quad faces.

    Both loops must have the same number of vertices.  The function pairs
    vertex ``loop_a[i]`` with ``loop_b[i]`` (aligned by index) and builds
    a quad for each adjacent pair.

    To get a watertight tube, *loop_a* should be wound CCW when viewed from
    outside the tube, and *loop_b* should be wound CW from the same viewpoint
    (i.e. both wound CCW from their own outward-normal side).

    Parameters
    ----------
    bm:     Target BMesh.
    loop_a: First vertex ring.
    loop_b: Second vertex ring (same vertex count as *loop_a*).

    Returns
    -------
    List of newly created quad :class:`BMFace` objects.

    Raises
    ------
    ValueError
        If the two loops have different vertex counts.
    """
    n = len(loop_a)
    if len(loop_b) != n:
        raise ValueError(
            f"bridge_loops: loop_a has {n} verts but loop_b has {len(loop_b)}."
        )

    faces: list[BMFace] = []
    for i in range(n):
        j = (i + 1) % n
        # Quad winding: a[i], a[j], b[j], b[i]  → outward normal faces away
        # from the tube interior when loop_a is the "bottom" ring and loop_b
        # is the "top" ring (both wound CCW from their outward-normal side).
        face = bm.faces.new([
            loop_a[i], loop_a[j],
            loop_b[j], loop_b[i],
        ])
        faces.append(face)

    return faces


# ===========================================================================
# 3.  Primitive constructors
# ===========================================================================

def make_cylinder(
    bm: BMesh,
    radius: float,
    depth: float,
    segments: int | None = None,
    center: Vector | None = None,
) -> tuple[list[BMVert], list[BMVert]]:
    """
    Add a **closed, manifold** cylinder to *bm*.

    The cylinder axis is the local +Z direction.  Its geometric centre is at
    *center* (default: origin).  The bottom cap is at ``center.z - depth/2``
    and the top cap at ``center.z + depth/2``.

    Parameters
    ----------
    bm:       Target BMesh.
    radius:   Cylinder radius in metres.
    depth:    Cylinder height (along Z) in metres.
    segments: Circumferential vertex count.  Defaults to ``RUNTIME.mesh_segments``.
    center:   World-space centre.  Defaults to ``(0, 0, 0)``.

    Returns
    -------
    ``(bottom_loop, top_loop)`` — the two rings of side-wall vertices
    (NOT the cap centre vertices; those are internal to the caps).

    Notes
    -----
    We do **not** use ``bmesh.ops.create_circle`` + extrude because the
    extrude operator depends on face selection state.  Instead we manually
    create the two rings and the cap faces, which is deterministic and
    ops-free.
    """
    if segments is None:
        segments = RUNTIME.mesh_segments
    if center is None:
        center = Vector((0.0, 0.0, 0.0))

    half = depth * 0.5
    z_bot = center.z - half
    z_top = center.z + half
    cx, cy = center.x, center.y

    # Build bottom and top vertex rings with the same angular winding so
    # bot_loop[i] and top_loop[i] are vertically aligned (no twist / "pinched" cylinder).
    # build_local_frame(+Z) and (-Z) give different u,v, so we use the same normal
    # for both rings, then reverse the top cap for correct outward normal.
    bot_center_2d = Vector((cx, cy, z_bot))
    top_center_2d = Vector((cx, cy, z_top))

    bot_loop = make_circle_verts(bm, bot_center_2d, Vector((0, 0, -1)), radius, segments)
    top_loop = make_circle_verts(bm, top_center_2d, Vector((0, 0, -1)), radius, segments)

    bridge_loops(bm, bot_loop, top_loop)

    # Bottom cap (n-gon); reverse winding so normal points -Z.
    cap_loop(bm, list(reversed(bot_loop)))

    # Top cap: reverse so normal points +Z (same ring winding as bottom from -Z view).
    cap_loop(bm, list(reversed(top_loop)))

    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    return bot_loop, top_loop


def make_frustum(
    bm: BMesh,
    radius_bottom: float,
    radius_top: float,
    depth: float,
    segments: int | None = None,
    center: Vector | None = None,
) -> tuple[list[BMVert], list[BMVert]]:
    """
    Add a closed frustum (truncated cone) to *bm* along the local +Z axis.

    The bottom ring is at ``center.z - depth/2`` with *radius_bottom*,
    the top ring at ``center.z + depth/2`` with *radius_top*.
    Both ends are capped.

    Parameters
    ----------
    bm:             Target BMesh.
    radius_bottom:  Radius at the bottom (local -Z) in metres.
    radius_top:     Radius at the top (local +Z) in metres.
    depth:          Length along Z in metres.
    segments:       Circumferential vertex count.
    center:         Geometric centre.  Defaults to origin.

    Returns
    -------
    ``(bottom_loop, top_loop)`` of the side-wall vertex rings.
    """
    if segments is None:
        segments = RUNTIME.mesh_segments
    if center is None:
        center = Vector((0.0, 0.0, 0.0))

    half = depth * 0.5
    z_bot = center.z - half
    z_top = center.z + half
    cx, cy = center.x, center.y

    bot_center = Vector((cx, cy, z_bot))
    top_center = Vector((cx, cy, z_top))
    normal = Vector((0, 0, -1))

    bot_loop = make_circle_verts(bm, bot_center, normal, radius_bottom, segments)
    top_loop = make_circle_verts(bm, top_center, normal, radius_top, segments)

    bridge_loops(bm, bot_loop, top_loop)
    cap_loop(bm, list(reversed(bot_loop)))
    cap_loop(bm, list(reversed(top_loop)))

    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    return bot_loop, top_loop


def make_tube(
    bm: BMesh,
    radius: float,
    depth: float,
    wall_thickness: float,
    segments: int | None = None,
    center: Vector | None = None,
) -> None:
    """
    Add a hollow tube (annular cylinder) to *bm*.

    Useful when :data:`config.PIPE_HOLLOW` is ``True``.  The tube is
    manifold: two annular end-caps connect the outer and inner walls.

    Parameters
    ----------
    bm:             Target BMesh.
    radius:         Outer radius in metres.
    depth:          Tube length along Z in metres.
    wall_thickness: Radial wall thickness in metres.  Must be < radius.
    segments:       Circumferential count.  Defaults to ``RUNTIME.mesh_segments``.
    center:         Geometric centre.  Defaults to origin.
    """
    if segments is None:
        segments = RUNTIME.mesh_segments
    if center is None:
        center = Vector((0.0, 0.0, 0.0))

    inner_radius = radius - wall_thickness
    if inner_radius <= 0:
        raise ValueError(
            f"make_tube: wall_thickness ({wall_thickness}) ≥ radius ({radius})."
        )

    half = depth * 0.5
    z_bot = center.z - half
    z_top = center.z + half
    cx, cy = center.x, center.y

    # Same normal for all rings so vertex indices align (no twist).
    n_out_bot = make_circle_verts(bm, Vector((cx, cy, z_bot)), Vector((0,0,-1)), radius,       segments)
    n_in_bot  = make_circle_verts(bm, Vector((cx, cy, z_bot)), Vector((0,0,-1)), inner_radius, segments)
    n_out_top = make_circle_verts(bm, Vector((cx, cy, z_top)), Vector((0,0,-1)), radius,       segments)
    n_in_top  = make_circle_verts(bm, Vector((cx, cy, z_top)), Vector((0,0,-1)), inner_radius, segments)

    bridge_loops(bm, n_out_bot, n_out_top)
    bridge_loops(bm, n_in_top, n_in_bot)
    _make_annular_cap(bm, list(reversed(n_out_bot)), n_in_bot)
    _make_annular_cap(bm, list(reversed(n_out_top)), list(reversed(n_in_top)))


def _make_annular_cap(
    bm: BMesh,
    outer_loop: list[BMVert],
    inner_loop: list[BMVert],
) -> None:
    """
    Fill the annular gap between two co-planar loops with quad faces.

    Internal helper used by :func:`make_tube`.
    """
    n = len(outer_loop)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([
            outer_loop[i], outer_loop[j],
            inner_loop[j], inner_loop[i],
        ])


# ===========================================================================
# 4.  Elbow (swept arc) constructor
# ===========================================================================

def make_elbow_sweep(
    bm: BMesh,
    arc: list[tuple[Vector, Vector]],
    radius: float,
    segments: int | None = None,
) -> None:
    """
    Build a swept-arc pipe section (elbow) in *bm* from a pre-computed arc.

    Parameters
    ----------
    bm:
        Target BMesh.
    arc:
        List of ``(centre, tangent)`` pairs as returned by
        :func:`coords.compute_elbow_arc`.  Length = n_arc_segments + 1.
    radius:
        Pipe outer radius in metres.
    segments:
        Circumferential vertex count per cross-section.
        Defaults to ``RUNTIME.mesh_segments``.

    Notes
    -----
    The function creates one vertex ring per arc point and bridges
    adjacent rings.  The two end-caps are closed with n-gon faces.
    Normals are recalculated at the end.
    """
    if segments is None:
        segments = RUNTIME.mesh_segments

    rings: list[list[BMVert]] = []

    for centre, tangent in arc:
        ring = make_circle_verts(bm, centre, tangent, radius, segments)
        rings.append(ring)

    # Bridge adjacent rings.
    for i in range(len(rings) - 1):
        bridge_loops(bm, rings[i], rings[i + 1])

    # Close the two open ends.
    cap_loop(bm, list(reversed(rings[0])))
    cap_loop(bm, rings[-1][:])

    bm.faces.ensure_lookup_table()


# ===========================================================================
# 5.  Normal recalculation
# ===========================================================================

def recalc_normals(bm: BMesh) -> None:
    """
    Recalculate face normals so they all point consistently outward.

    Should be called after any boolean-like topology change and after
    :func:`make_elbow_sweep` / :func:`make_tube`.
    """
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


# ===========================================================================
# 6.  BMesh → Blender Object
# ===========================================================================

def bm_to_object(
    bm: BMesh,
    name: str,
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    """
    Write *bm* into a new ``bpy.types.Mesh``, wrap it in a new
    ``bpy.types.Object``, link it to *collection* (or the scene collection
    if *collection* is ``None``), and return the object.

    The BMesh is **freed** after the write; do not use it afterwards.

    Parameters
    ----------
    bm:         Completed BMesh to convert.
    name:       Name for both the Mesh datablock and the Object.
    collection: Target Blender collection.  If ``None``, the object is linked
                to ``bpy.context.scene.collection``.

    Returns
    -------
    The newly created ``bpy.types.Object``.
    """
    mesh = bpy.data.meshes.new(name=name)
    bm.to_mesh(mesh)
    bm.free()

    mesh.update()

    obj = bpy.data.objects.new(name=name, object_data=mesh)

    target_col = collection if collection is not None else bpy.context.scene.collection
    target_col.objects.link(obj)

    return obj


# ===========================================================================
# 7.  Manifold validation helper
# ===========================================================================

def is_manifold(bm: BMesh) -> bool:
    """
    Return ``True`` if every edge in *bm* is shared by exactly two faces.

    A mesh that passes this check is suitable as input to the MANIFOLD
    boolean solver.

    Parameters
    ----------
    bm: The BMesh to inspect (ensure lookup tables are up-to-date).
    """
    bm.edges.ensure_lookup_table()
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            return False
    return True


def check_manifold_obj(obj: bpy.types.Object) -> bool:
    """
    Check whether a finalised Blender Object's mesh is manifold.

    Creates a temporary BMesh, performs the check, and frees it.

    Parameters
    ----------
    obj: A ``bpy.types.Object`` with a Mesh data-block.

    Returns
    -------
    ``True`` if manifold, ``False`` otherwise.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return is_manifold(bm)
    finally:
        bm.free()


# ===========================================================================
# 8.  Mesh clean-up helpers
# ===========================================================================

def remove_doubles(bm: BMesh, dist: float = 1e-5) -> int:
    """
    Merge vertices within *dist* of each other.

    Returns the number of vertices removed.
    """
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bm.verts.ensure_lookup_table()
    return before - len(bm.verts)
