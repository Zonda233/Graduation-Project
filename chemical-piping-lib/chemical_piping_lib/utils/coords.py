"""
coords.py
=========
Coordinate-system utilities for the chemical-piping-lib.

Responsibilities
----------------
* Convert between voxel integer coordinates and world-space float coordinates.
* Translate axis-direction strings (e.g. ``"+X"``) to ``mathutils.Vector``.
* Compute rotation quaternions that align one direction to another.
* Compute the sequence of cross-section centres and normals that define an
  elbow (bent pipe) arc — the most mathematically involved helper in the lib.

Design constraints
------------------
* This module is the **only** place that performs non-trivial 3-D maths.
* It depends only on ``mathutils`` (bundled with Blender) and ``config``.
* It must be importable outside Blender for unit-testing (``mathutils`` is
  available as a standalone PyPI package for that purpose).

Coordinate convention
---------------------
* Right-handed, Z-up (matches Blender default).
* Voxel (i, j, k) refers to the *corner* at the minimum-coordinate vertex
  of that voxel cell; its *centre* is at (i+0.5, j+0.5, k+0.5) * voxel_size.
"""

from __future__ import annotations

import math
from typing import Sequence

from mathutils import Matrix, Quaternion, Vector

from chemical_piping_lib.config import RUNTIME, VALID_AXES


# ===========================================================================
# 1.  Axis string → Vector
# ===========================================================================

# Static lookup table.  Built once at import time.
_AXIS_VECTOR: dict[str, Vector] = {
    "+X": Vector(( 1.0,  0.0,  0.0)),
    "-X": Vector((-1.0,  0.0,  0.0)),
    "+Y": Vector(( 0.0,  1.0,  0.0)),
    "-Y": Vector(( 0.0, -1.0,  0.0)),
    "+Z": Vector(( 0.0,  0.0,  1.0)),
    "-Z": Vector(( 0.0,  0.0, -1.0)),
}


def axis_to_vec(axis: str) -> Vector:
    """
    Return the unit ``Vector`` for a direction string.

    Parameters
    ----------
    axis:
        One of ``"+X"``, ``"-X"``, ``"+Y"``, ``"-Y"``, ``"+Z"``, ``"-Z"``.

    Returns
    -------
    A *copy* of the corresponding unit vector (safe to mutate).

    Raises
    ------
    ValueError
        For any unrecognised string.
    """
    if axis not in _AXIS_VECTOR:
        raise ValueError(
            f"Unknown axis string {axis!r}. Valid values: {VALID_AXES}."
        )
    return _AXIS_VECTOR[axis].copy()


# ===========================================================================
# 2.  Voxel ↔ world-space conversions
# ===========================================================================

def vc_to_wc_center(vc: Sequence[int]) -> Vector:
    """
    Convert voxel integer coordinate to the world-space *centre* of that voxel.

    Uses the runtime voxel size and origin from :data:`config.RUNTIME`.

    Parameters
    ----------
    vc:
        Integer triplet ``(i, j, k)`` — voxel grid indices.

    Returns
    -------
    World-space centre as a ``mathutils.Vector``.

    Examples
    --------
    >>> vc_to_wc_center((0, 0, 0))
    Vector((0.1, 0.1, 0.1))   # for default VOXEL_SIZE = 0.2
    """
    ox, oy, oz = RUNTIME.origin_wc
    vs = RUNTIME.voxel_size
    return Vector((
        ox + (vc[0] + 0.5) * vs,
        oy + (vc[1] + 0.5) * vs,
        oz + (vc[2] + 0.5) * vs,
    ))


def vc_to_wc_point(vc: Sequence[float]) -> Vector:
    """
    Convert an arbitrary point expressed in voxel-grid coordinates to
    world space.

    Unlike :func:`vc_to_wc_center`, this function does **not** add the
    half-voxel offset. It is therefore appropriate for:

    * bounding-box centres already computed in voxel units
    * fractional coordinates
    * explicit geometric points on the voxel grid
    """
    ox, oy, oz = RUNTIME.origin_wc
    vs = RUNTIME.voxel_size
    return Vector((
        ox + float(vc[0]) * vs,
        oy + float(vc[1]) * vs,
        oz + float(vc[2]) * vs,
    ))


def vc_to_wc_corner(vc: Sequence[int]) -> Vector:
    """
    Convert voxel integer coordinate to the world-space *minimum corner*
    (i.e. the vertex at the lowest X, Y, Z) of that voxel.
    """
    ox, oy, oz = RUNTIME.origin_wc
    vs = RUNTIME.voxel_size
    return Vector((
        ox + vc[0] * vs,
        oy + vc[1] * vs,
        oz + vc[2] * vs,
    ))


def wc_to_vc(wc: Sequence[float]) -> tuple[int, int, int]:
    """
    Snap a world-space point to the voxel grid, returning the voxel index
    whose *centre* is closest to the given point.

    Parameters
    ----------
    wc:
        World-space coordinate ``(x, y, z)`` in metres.

    Returns
    -------
    Integer voxel index ``(i, j, k)``.
    """
    ox, oy, oz = RUNTIME.origin_wc
    vs = RUNTIME.voxel_size
    return (
        int(math.floor((wc[0] - ox) / vs)),
        int(math.floor((wc[1] - oy) / vs)),
        int(math.floor((wc[2] - oz) / vs)),
    )


# ===========================================================================
# 3.  Rotation helpers
# ===========================================================================

#: The canonical "build axis": every asset is constructed pointing along +Z
#: and then rotated to its target direction.
_BUILD_AXIS: Vector = Vector((0.0, 0.0, 1.0))

#: Small epsilon for floating-point direction comparisons.
_EPS: float = 1e-7


def rotation_from_build_axis(target: Vector) -> Quaternion:
    """
    Compute the quaternion that rotates the canonical build axis (``+Z``)
    to align with *target*.

    Special cases
    -------------
    * If *target* is already ``+Z``, the identity quaternion is returned.
    * If *target* is exactly ``-Z``, a 180° rotation around ``+X`` is
      returned (``rotation_difference`` would give an arbitrary axis).

    Parameters
    ----------
    target:
        Destination direction (need not be unit length; it is normalised
        internally).

    Returns
    -------
    Unit quaternion.
    """
    t = target.normalized()

    # Already aligned — identity.
    if (_BUILD_AXIS - t).length < _EPS:
        return Quaternion()  # identity

    # Anti-parallel — 180° around X to avoid degenerate cross product.
    if (_BUILD_AXIS + t).length < _EPS:
        return Quaternion((0.0, 1.0, 0.0, 0.0))  # 180° around X

    return _BUILD_AXIS.rotation_difference(t)


def rotation_from_axis_str(axis: str) -> Quaternion:
    """
    Convenience wrapper: convert an axis string directly to a build-axis
    alignment quaternion.

    >>> q = rotation_from_axis_str("+X")
    """
    return rotation_from_build_axis(axis_to_vec(axis))


def align_object_to_axis(obj, axis: str) -> None:
    """
    Rotate a ``bpy.types.Object`` so that its local +Z points along *axis*.

    The object's ``rotation_mode`` is set to ``'QUATERNION'`` to avoid
    Euler gimbal-lock.

    Parameters
    ----------
    obj:
        A ``bpy.types.Object`` (type hint omitted to keep this importable
        outside Blender).
    axis:
        Direction string, e.g. ``"+X"``.
    """
    q = rotation_from_axis_str(axis)
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = q


# ===========================================================================
# 4.  Elbow arc geometry
# ===========================================================================

def compute_elbow_arc(
    corner_wc: Vector,
    axis_in:   str,
    axis_out:  str,
    bend_radius: float,
    n_segments:  int | None = None,
) -> list[tuple[Vector, Vector]]:
    """
    Compute the sequence of ``(centre, tangent)`` pairs that describe the
    centre-line arc of a bent pipe.

    The arc lives in the plane spanned by *axis_in* and *axis_out*.
    The pipe arrives at *corner_wc* travelling in the *axis_in* direction and
    departs in the *axis_out* direction.

    Mathematical derivation
    -----------------------
    Let::

        d_in  = unit vector of axis_in   (e.g. +Z = (0,0,1))
        d_out = unit vector of axis_out  (e.g. +X = (1,0,0))

    The centre of the bending circle is at::

        O = corner_wc
            - R * d_in    # step back along incoming direction
            + R * d_out   # step forward along outgoing direction

    This places O such that:
        * |O - corner_wc| = R * sqrt(2)  (for 90° bend)
        * The arc from the in-tangent point to the out-tangent point
          passes through the geometric corner.

    The in-tangent point (where straight pipe ends)  P_in  = corner_wc - R * d_in
    The out-tangent point (where straight pipe begins) P_out = corner_wc + R * d_out

    We then parametrically sweep from P_in to P_out around O.

    Parameters
    ----------
    corner_wc:
        World-space position of the voxel corner (the geometric bend point).
    axis_in:
        Direction the pipe travels *into* the bend (e.g. ``"+Z"``).
    axis_out:
        Direction the pipe travels *out of* the bend (e.g. ``"+X"``).
    bend_radius:
        Radius of the bending circle (centre-line radius), in metres.
        Industry standard is 1.5× nominal pipe diameter.
    n_segments:
        Number of arc subdivisions.  Defaults to ``RUNTIME.elbow_arc_segments``.

    Returns
    -------
    List of ``(centre: Vector, tangent: Vector)`` tuples, length = n_segments+1.
    The *tangent* at each point is the unit vector along the pipe axis
    (i.e. the direction a cross-section face should point outward).

    Raises
    ------
    ValueError
        If *axis_in* and *axis_out* are parallel (straight pipe) or
        anti-parallel (180° bend — use two 90° elbows instead).
    """
    if n_segments is None:
        n_segments = RUNTIME.elbow_arc_segments

    d_in  = axis_to_vec(axis_in)
    d_out = axis_to_vec(axis_out)

    dot = d_in.dot(d_out)

    if abs(dot - 1.0) < _EPS:
        raise ValueError(
            f"axis_in ({axis_in}) and axis_out ({axis_out}) are identical: "
            "that is a straight pipe, not an elbow."
        )
    if abs(dot + 1.0) < _EPS:
        raise ValueError(
            f"axis_in ({axis_in}) and axis_out ({axis_out}) are anti-parallel "
            "(180° bend).  Model this as two consecutive 90° elbows."
        )

    R = bend_radius

    # --- Bending-circle centre -------------------------------------------
    # Tangent points on the arc:
    P_in  = corner_wc - R * d_in    # where straight incoming pipe ends
    P_out = corner_wc + R * d_out   # where straight outgoing pipe begins

    # The bending-circle centre O satisfies:
    #   O = P_in  + R * n_in
    #   O = P_out + R * n_out
    # where n_in and n_out point radially inward (perpendicular to the pipe
    # axis, lying in the bend plane).
    #
    # For a 90° bend with orthogonal d_in / d_out the maths simplifies to:
    #   O = corner_wc - R * d_in + R * d_out
    # which holds for any angle because the tangent-point construction is
    # exact by definition.
    O = corner_wc.copy() - R * d_in + R * d_out

    # --- Parametric sweep ------------------------------------------------
    # Vector from O to P_in (start of arc), and from O to P_out (end of arc).
    r_start = (P_in  - O).normalized()  # unit radial vector at arc start
    r_end   = (P_out - O).normalized()  # unit radial vector at arc end

    # Total arc angle (using the dot product of the two radial vectors).
    cos_theta = max(-1.0, min(1.0, r_start.dot(r_end)))
    theta = math.acos(cos_theta)        # in radians, always in (0, π]

    # Rotation axis (normal to the bend plane).
    rot_axis = r_start.cross(r_end)
    if rot_axis.length < _EPS:
        raise ValueError("Degenerate elbow: bend-plane normal is zero vector.")
    rot_axis.normalize()

    results: list[tuple[Vector, Vector]] = []

    for i in range(n_segments + 1):
        t = i / n_segments              # 0.0 … 1.0
        angle = t * theta

        # Rotate r_start by `angle` around rot_axis.
        rot_mat = Matrix.Rotation(angle, 3, rot_axis)
        r_i = rot_mat @ r_start         # radial unit vector at step i

        centre_i = O + R * r_i          # point on the arc centre-line

        # Tangent = derivative of centre w.r.t. angle, normalised.
        # d/d(angle) [O + R * rot(r_start)] = R * (rot_axis × r_i)
        tangent_i = rot_axis.cross(r_i).normalized()

        results.append((centre_i.copy(), tangent_i.copy()))

    return results


# ===========================================================================
# 5.  Miscellaneous geometry helpers
# ===========================================================================

def midpoint(a: Vector, b: Vector) -> Vector:
    """Return the midpoint between two vectors."""
    return (a + b) * 0.5


def perpendicular_vector(v: Vector) -> Vector:
    """
    Return an arbitrary unit vector perpendicular to *v*.

    This is useful for constructing a local coordinate frame when only
    one axis is known.

    The algorithm picks the world axis least aligned with *v*, then
    applies Gram-Schmidt orthogonalisation.
    """
    v = v.normalized()
    # Choose the world axis least parallel to v.
    candidates = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
    ref = min(candidates, key=lambda c: abs(v.dot(c)))
    perp = v.cross(ref)
    perp.normalize()
    return perp


def build_local_frame(normal: Vector) -> tuple[Vector, Vector]:
    """
    Given a *normal* (the axis a circular cross-section faces), compute two
    orthogonal in-plane unit vectors (u, v) that span the cross-section plane.

    Returns
    -------
    ``(u, v)`` — both unit vectors, both perpendicular to *normal* and to
    each other.
    """
    u = perpendicular_vector(normal)
    v_vec = normal.cross(u).normalized()
    return u, v_vec
