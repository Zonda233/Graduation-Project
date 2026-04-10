"""
Schema validation tests: all example and test JSON files must conform to protocol_v1.

Run with: pytest tests/test_schema_validation.py -v
No Blender required. Requires: pip install jsonschema
"""

import json
from pathlib import Path

import pytest
import jsonschema

# Schema lives next to the package
PKG_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PKG_ROOT / "chemical_piping_lib" / "schema" / "protocol_v1.json"
EXAMPLES_DIR = PKG_ROOT / "examples"


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def json_files_to_validate():
    """All .json under examples/ that are protocol inputs (exclude non-protocol if any)."""
    if not EXAMPLES_DIR.exists():
        return []
    return list(EXAMPLES_DIR.glob("*.json"))


@pytest.fixture(scope="module")
def schema():
    return load_schema()


@pytest.mark.parametrize("json_path", json_files_to_validate(), ids=lambda p: p.name)
def test_example_json_conforms_to_schema(schema, json_path):
    """Each example JSON must validate against the protocol schema."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    # Strip comments / non-protocol keys if present; schema has additionalProperties: true
    # so _comment keys are fine. Validate.
    jsonschema.validate(instance=data, schema=schema)


def test_schema_loads_and_has_required_top_level():
    """Sanity check: schema defines meta, materials, assets, tee_joints, segments."""
    schema = load_schema()
    assert "properties" in schema
    for key in ["meta", "materials", "assets", "tee_joints", "segments"]:
        assert key in schema["properties"]
    assert "required" in schema
    assert set(schema["required"]) == {"meta", "materials", "assets", "tee_joints", "segments"}
