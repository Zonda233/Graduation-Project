"""
Unit tests for chemical_piping_lib.config.

All tests run without Blender. Validates DN/flange lookups and invariants.
"""

import pytest

from chemical_piping_lib.config import (
    DN_TABLE,
    FLANGE_TABLE,
    MATERIAL_PRESETS,
    get_dn_spec,
    get_flange_spec,
    VOXEL_SIZE,
    ORIGIN_WC,
    GRID_DIMENSIONS,
)


# ---------------------------------------------------------------------------
# DN table
# ---------------------------------------------------------------------------

def test_get_dn_spec_dn100():
    """DN100 nominal 0.1 m → outer_diameter and wall_thickness from table."""
    spec = get_dn_spec(0.1)
    assert spec["outer_diameter"] == pytest.approx(0.11430, rel=1e-4)
    assert spec["wall_thickness"] == pytest.approx(0.00600, rel=1e-4)


def test_get_dn_spec_dn50():
    """DN50 nominal 0.05 m."""
    spec = get_dn_spec(0.05)
    assert spec["outer_diameter"] == pytest.approx(0.06033, rel=1e-4)


def test_get_dn_spec_tolerance_within_20_percent():
    """Slightly off nominal still maps to nearest DN."""
    # 0.048 is between DN40 and DN50; nearest is DN50 (0.05)
    spec = get_dn_spec(0.048)
    assert "outer_diameter" in spec
    assert "wall_thickness" in spec


def test_get_dn_spec_rejects_far():
    """Nominal diameter >20% from any DN raises ValueError."""
    with pytest.raises(ValueError, match="No DN specification found"):
        get_dn_spec(10.0)  # way above DN500
    with pytest.raises(ValueError, match="No DN specification found"):
        get_dn_spec(0.001)  # way below DN15


def test_dn_table_has_expected_keys():
    """DN_TABLE contains standard sizes used in protocol."""
    for label in ["DN25", "DN50", "DN100", "DN150", "DN200"]:
        assert label in DN_TABLE
        assert "outer_diameter" in DN_TABLE[label]
        assert "wall_thickness" in DN_TABLE[label]


# ---------------------------------------------------------------------------
# Flange table
# ---------------------------------------------------------------------------

def test_get_flange_spec_dn100():
    """Flange spec for DN100."""
    spec = get_flange_spec(0.1)
    assert spec["outer_diameter"] == pytest.approx(0.220, rel=1e-4)
    assert "thickness" in spec
    assert "bolt_count" in spec


def test_get_flange_spec_nearest_match():
    """Nearest DN in FLANGE_TABLE is returned (no rejection; 0.015 → DN25)."""
    spec = get_flange_spec(0.015)
    assert "outer_diameter" in spec
    # DN25 is closest to 0.015 in FLANGE_TABLE
    assert spec["outer_diameter"] == pytest.approx(0.115, rel=1e-4)


def test_flange_table_subset_of_dn():
    """Every flange size should have a corresponding DN pipe size."""
    for dn_label in FLANGE_TABLE:
        assert dn_label in DN_TABLE


# ---------------------------------------------------------------------------
# Material presets
# ---------------------------------------------------------------------------

def test_material_presets_required_ids():
    """Presets referenced in doc (and built-in) exist."""
    for key in ["carbon_steel", "stainless_steel", "valve_body", "default"]:
        assert key in MATERIAL_PRESETS
        p = MATERIAL_PRESETS[key]
        assert "base_color" in p
        assert "metallic" in p
        assert "roughness" in p
        assert len(p["base_color"]) == 4


# ---------------------------------------------------------------------------
# Constants (invariants)
# ---------------------------------------------------------------------------

def test_voxel_defaults():
    """Default voxel grid matches protocol doc."""
    assert VOXEL_SIZE == 0.2
    assert ORIGIN_WC == (0.0, 0.0, 0.0)
    assert GRID_DIMENSIONS == (20, 20, 20)
