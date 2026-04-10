"""
Unit tests for chemical_piping_lib.utils.coords.

Uses mathutils (available as standalone PyPI package outside Blender).
RUNTIME is reset in conftest so voxel_size/origin are defaults.
"""

import pytest
from mathutils import Vector

from chemical_piping_lib.config import RUNTIME, VOXEL_SIZE, ORIGIN_WC
from chemical_piping_lib.config import VALID_AXES
from chemical_piping_lib.utils.coords import (
    axis_to_vec,
    vc_to_wc_center,
    vc_to_wc_corner,
    wc_to_vc,
)


# ---------------------------------------------------------------------------
# Axis ↔ Vector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("axis", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
def test_axis_to_vec_unit_length(axis):
    """Every axis string yields a unit vector."""
    v = axis_to_vec(axis)
    assert v.length == pytest.approx(1.0, rel=1e-6)


@pytest.mark.parametrize("axis,expected", [
    ("+X", (1, 0, 0)),
    ("-X", (-1, 0, 0)),
    ("+Z", (0, 0, 1)),
    ("-Z", (0, 0, -1)),
])
def test_axis_to_vec_values(axis, expected):
    """Known axis → vector mapping."""
    v = axis_to_vec(axis)
    assert (v.x, v.y, v.z) == expected


def test_axis_to_vec_invalid_raises():
    """Invalid axis string raises ValueError."""
    with pytest.raises(ValueError, match="Unknown axis"):
        axis_to_vec("+W")


def test_valid_axes_complete():
    """VALID_AXES contains exactly the six axis strings."""
    assert set(VALID_AXES) == {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}
    assert len(VALID_AXES) == 6


# ---------------------------------------------------------------------------
# Voxel ↔ World (default RUNTIME: origin 0,0,0, voxel_size 0.2)
# ---------------------------------------------------------------------------

def test_vc_to_wc_center_origin_voxel():
    """vc (0,0,0) → world centre 0.1, 0.1, 0.1 for voxel_size 0.2."""
    RUNTIME.reset()
    wc = vc_to_wc_center((0, 0, 0))
    assert wc.x == pytest.approx(0.1)
    assert wc.y == pytest.approx(0.1)
    assert wc.z == pytest.approx(0.1)


def test_vc_to_wc_center_formula():
    """wc = origin_wc + (vc + 0.5) * voxel_size (doc formula)."""
    RUNTIME.reset()
    vc = (2, 3, 1)
    wc = vc_to_wc_center(vc)
    expected = (
        ORIGIN_WC[0] + (vc[0] + 0.5) * VOXEL_SIZE,
        ORIGIN_WC[1] + (vc[1] + 0.5) * VOXEL_SIZE,
        ORIGIN_WC[2] + (vc[2] + 0.5) * VOXEL_SIZE,
    )
    assert wc.x == pytest.approx(expected[0])
    assert wc.y == pytest.approx(expected[1])
    assert wc.z == pytest.approx(expected[2])


def test_vc_to_wc_corner_no_half_offset():
    """vc_to_wc_corner gives minimum corner of voxel (no +0.5)."""
    RUNTIME.reset()
    wc = vc_to_wc_corner((0, 0, 0))
    assert wc.x == pytest.approx(0.0)
    assert wc.y == pytest.approx(0.0)
    assert wc.z == pytest.approx(0.0)
    wc1 = vc_to_wc_corner((1, 0, 0))
    assert wc1.x == pytest.approx(0.2)


def test_wc_to_vc_roundtrip_center():
    """wc from vc_to_wc_center round-trips back to same vc."""
    RUNTIME.reset()
    for vc in [(0, 0, 0), (1, 1, 1), (5, 3, 2)]:
        wc = vc_to_wc_center(vc)
        vc_back = wc_to_vc((wc.x, wc.y, wc.z))
        assert vc_back == vc


def test_wc_to_vc_closest_center():
    """wc_to_vc returns voxel whose centre is closest (floor semantics)."""
    RUNTIME.reset()
    # Centre of (1,1,1) is (0.3, 0.3, 0.3). Slightly below centre should still map to (1,1,1).
    vc = wc_to_vc((0.29, 0.29, 0.29))
    assert vc == (1, 1, 1)


def test_runtime_override_applied():
    """When RUNTIME is overridden, conversions use new origin/size."""
    RUNTIME.reset()
    RUNTIME.apply_meta({
        "voxel_grid": {
            "voxel_size": 0.5,
            "origin_wc": [1.0, 0.0, 0.0],
            "dimensions": [10, 10, 10],
        }
    })
    wc = vc_to_wc_center((0, 0, 0))
    # origin + (0.5 * 0.5) = 1 + 0.25 = 1.25
    assert wc.x == pytest.approx(1.25)
    assert wc.y == pytest.approx(0.25)
    assert wc.z == pytest.approx(0.25)
