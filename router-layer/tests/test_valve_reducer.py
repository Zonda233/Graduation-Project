"""
test_valve_reducer.py
=====================
Unit tests for Track A (InlineReducer) and Track B (valve_subtype) injection.

Runs without Blender — only exercises the router layer in isolation.

Usage (from project root):
    python router-layer/tests/test_valve_reducer.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: add router-layer to sys.path so relative imports work
# ---------------------------------------------------------------------------
SCRIPT_DIR       = Path(__file__).resolve().parent
ROUTER_LAYER_DIR = SCRIPT_DIR.parent
PROJECT_ROOT     = ROUTER_LAYER_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load the router-layer package via the bridge helper (same as the main test)
import importlib.util

def _load_bridge():
    bridge_path = ROUTER_LAYER_DIR / "bridge" / "generation_bridge.py"
    mod_name = "router_layer.bridge.generation_bridge"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, str(bridge_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

bridge = _load_bridge()
bridge.load_router_layer_package(ROUTER_LAYER_DIR)

# Now we can import router-layer internals
from router_layer.emission.path_converter import GenerationPathComponentConverter  # type: ignore
from router_layer.emission.geometry_trimmer import PipeAndTeeGeometryTrimmer       # type: ignore
from router_layer.config import RouterConfig                                        # type: ignore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(voxel_size: float = 0.2) -> RouterConfig:
    return RouterConfig(
        voxel_size=voxel_size,
        grid_dimensions=(20, 20, 20),
        origin_wc=(0.0, 0.0, 0.0),
    )


def _make_converter(voxel_size: float = 0.2) -> GenerationPathComponentConverter:
    cfg = _make_config(voxel_size)
    trimmer = PipeAndTeeGeometryTrimmer(cfg)
    return GenerationPathComponentConverter(cfg, trimmer)


# ---------------------------------------------------------------------------
# Track B — valve_subtype midpoint injection
# ---------------------------------------------------------------------------

def test_valve_gate_injected_at_midpoint():
    """A Gate valve should appear at the midpoint voxel of a straight path."""
    conv = _make_converter()
    # 7-voxel straight path along +x: (0,0,0) → (6,0,0)
    path = [(x, 0, 0) for x in range(7)]
    mid_idx = len(path) // 2  # = 3  → voxel (3,0,0)

    components = conv.convert(
        path=path,
        segment_id="seg_test",
        nominal_diameter_m=0.08,
        valve_subtype="Gate",
    )

    types = [c["type"] for c in components]
    assert "Valve" in types, f"Expected Valve in components, got: {types}"

    valve = next(c for c in components if c["type"] == "Valve")
    assert valve["subtype"] == "Gate", f"Expected subtype Gate, got {valve['subtype']}"
    assert valve["vc_start"] == list(path[mid_idx]), (
        f"Valve vc_start should be midpoint {path[mid_idx]}, got {valve['vc_start']}"
    )
    assert valve["axis"] == "+X", f"Expected axis +X, got {valve['axis']}"
    print(f"  [PASS] test_valve_gate_injected_at_midpoint  (valve at vc {valve['vc_start']})")


def test_valve_ball_injected():
    """A Ball valve should appear with subtype Ball."""
    conv = _make_converter()
    path = [(0, y, 0) for y in range(5)]

    components = conv.convert(
        path=path,
        segment_id="seg_ball",
        nominal_diameter_m=0.05,
        valve_subtype="Ball",
    )

    valve = next((c for c in components if c["type"] == "Valve"), None)
    assert valve is not None, "Expected a Valve component"
    assert valve["subtype"] == "Ball"
    print(f"  [PASS] test_valve_ball_injected  (valve at vc {valve['vc_start']})")


def test_no_valve_without_subtype():
    """Without valve_subtype, no Valve component should be emitted."""
    conv = _make_converter()
    path = [(x, 0, 0) for x in range(5)]

    components = conv.convert(
        path=path,
        segment_id="seg_novalve",
        nominal_diameter_m=0.08,
    )

    types = [c["type"] for c in components]
    assert "Valve" not in types, f"Unexpected Valve in components: {types}"
    print(f"  [PASS] test_no_valve_without_subtype")


def test_valve_wc_start_end_span_one_voxel():
    """Valve wc_start and wc_end should span exactly one voxel (voxel_size apart)."""
    voxel_size = 0.2
    conv = _make_converter(voxel_size)
    path = [(x, 0, 0) for x in range(7)]

    components = conv.convert(
        path=path,
        segment_id="seg_wc",
        nominal_diameter_m=0.08,
        valve_subtype="Gate",
    )

    valve = next(c for c in components if c["type"] == "Valve")
    wc_start = valve["wc_start"]
    wc_end   = valve["wc_end"]
    # Along +x axis, wc_end[0] - wc_start[0] should equal voxel_size
    span = round(wc_end[0] - wc_start[0], 6)
    assert abs(span - voxel_size) < 1e-9, (
        f"Expected valve span {voxel_size} along x, got {span}"
    )
    print(f"  [PASS] test_valve_wc_start_end_span_one_voxel  (span={span})")


# ---------------------------------------------------------------------------
# Track A — InlineReducer injection
# ---------------------------------------------------------------------------

def test_reducer_injected_at_specified_voxel():
    """A Reducer should appear at the voxel listed in reducer_vcs."""
    conv = _make_converter()
    path = [(x, 0, 0) for x in range(7)]
    reducer_vc = (3, 0, 0)

    components = conv.convert(
        path=path,
        segment_id="seg_reducer",
        nominal_diameter_m=0.08,
        reducer_vcs={reducer_vc: {"diameter_in_m": 0.08, "diameter_out_m": 0.05}},
    )

    types = [c["type"] for c in components]
    assert "Reducer" in types, f"Expected Reducer in components, got: {types}"

    reducer = next(c for c in components if c["type"] == "Reducer")
    assert reducer["vc_start"] == list(reducer_vc), (
        f"Reducer vc_start should be {reducer_vc}, got {reducer['vc_start']}"
    )
    assert abs(reducer["diameter_in_m"]  - 0.08) < 1e-9
    assert abs(reducer["diameter_out_m"] - 0.05) < 1e-9
    print(f"  [PASS] test_reducer_injected_at_specified_voxel  (reducer at vc {reducer['vc_start']})")


def test_reducer_wc_span_one_voxel():
    """Reducer wc_start and wc_end should span exactly one voxel."""
    voxel_size = 0.2
    conv = _make_converter(voxel_size)
    path = [(x, 0, 0) for x in range(7)]
    reducer_vc = (3, 0, 0)

    components = conv.convert(
        path=path,
        segment_id="seg_reducer_wc",
        nominal_diameter_m=0.08,
        reducer_vcs={reducer_vc: {"diameter_in_m": 0.08, "diameter_out_m": 0.05}},
    )

    reducer = next(c for c in components if c["type"] == "Reducer")
    span = round(reducer["wc_end"][0] - reducer["wc_start"][0], 6)
    assert abs(span - voxel_size) < 1e-9, (
        f"Expected reducer span {voxel_size}, got {span}"
    )
    print(f"  [PASS] test_reducer_wc_span_one_voxel  (span={span})")


def test_no_reducer_without_reducer_vcs():
    """Without reducer_vcs, no Reducer component should be emitted."""
    conv = _make_converter()
    path = [(x, 0, 0) for x in range(5)]

    components = conv.convert(
        path=path,
        segment_id="seg_noreducer",
        nominal_diameter_m=0.08,
    )

    types = [c["type"] for c in components]
    assert "Reducer" not in types, f"Unexpected Reducer in components: {types}"
    print(f"  [PASS] test_no_reducer_without_reducer_vcs")


def test_valve_and_reducer_coexist():
    """Both Valve and Reducer can appear in the same segment."""
    conv = _make_converter()
    # 11-voxel path: valve at midpoint (5,0,0), reducer at (2,0,0)
    path = [(x, 0, 0) for x in range(11)]
    reducer_vc = (2, 0, 0)

    components = conv.convert(
        path=path,
        segment_id="seg_both",
        nominal_diameter_m=0.08,
        valve_subtype="Gate",
        reducer_vcs={reducer_vc: {"diameter_in_m": 0.08, "diameter_out_m": 0.05}},
    )

    types = [c["type"] for c in components]
    assert "Valve"   in types, f"Expected Valve in {types}"
    assert "Reducer" in types, f"Expected Reducer in {types}"
    print(f"  [PASS] test_valve_and_reducer_coexist  (types={types})")


# ---------------------------------------------------------------------------
# End-to-end: route a JSON with valve_subtype and verify output
# ---------------------------------------------------------------------------

# End-to-end router input using the parser's expected field names:
# nodes use "id"/"type"/"role" (top-level), lines use "id"/"from_node"/"to_node".
VALVE_ROUTER_INPUT = {
    "meta": {
        "schema_name": "router_input_v1",
        "units": {"length": "m"},
    },
    "nodes": [
        {
            "id": "port_a_out",
            "type": "EquipmentPort",
            "role": "outlet",
            "placement_hint": {
                "z_layers": [1],
                "anchor_policy": "near_seed",
            },
            "bbox_hint": {"extent_voxels": [1, 1, 1], "clearance_voxels": 1},
        },
        {
            "id": "port_b_in",
            "type": "EquipmentPort",
            "role": "inlet",
            "placement_hint": {
                "z_layers": [1],
                "anchor_policy": "near_seed",
            },
            "bbox_hint": {"extent_voxels": [1, 1, 1], "clearance_voxels": 1},
        },
    ],
    "lines": [
        {
            "id": "line_valve",
            "from_node": "port_a_out",
            "to_node": "port_b_in",
            "nominal_diameter_mm": 80,
            "valve_subtype": "Gate",
        }
    ],
    "constraints": {"routing_rules": {}},
}


def test_end_to_end_valve_in_output():
    """Full router pipeline: valve_subtype=Gate should produce a Valve component."""
    gen_json = bridge.route_to_generation_json(PROJECT_ROOT, VALVE_ROUTER_INPUT)

    all_components = []
    for seg in gen_json.get("segments", []):
        all_components.extend(seg.get("components", []))

    valve_comps = [c for c in all_components if c.get("type") == "Valve"]
    assert valve_comps, (
        "Expected at least one Valve component in generation JSON, "
        f"got component types: {[c.get('type') for c in all_components]}"
    )
    assert valve_comps[0]["subtype"] == "Gate"
    print(f"  [PASS] test_end_to_end_valve_in_output  "
          f"(found {len(valve_comps)} Valve component(s))")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_valve_gate_injected_at_midpoint,
    test_valve_ball_injected,
    test_no_valve_without_subtype,
    test_valve_wc_start_end_span_one_voxel,
    test_reducer_injected_at_specified_voxel,
    test_reducer_wc_span_one_voxel,
    test_no_reducer_without_reducer_vcs,
    test_valve_and_reducer_coexist,
    test_end_to_end_valve_in_output,
]


def main() -> None:
    print("=" * 60)
    print("  Valve / Reducer injection tests")
    print("=" * 60)
    passed = 0
    failed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {fn.__name__}: {exc}")
            failed += 1
    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 60)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
