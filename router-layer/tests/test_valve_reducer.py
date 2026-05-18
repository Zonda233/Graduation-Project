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
# Trim correctness — pipes adjacent to Valve/Reducer must end at component face
# ---------------------------------------------------------------------------

def test_valve_adjacent_pipes_trimmed_to_face():
    """Pipes on either side of a Valve must end/start at the valve's wc_start/wc_end.

    Before the fix, the pipe before the valve had wc_end = vc_to_wc(valve_vc)
    (the voxel centre), which extends into the valve body.  After the fix,
    wc_end must equal valve.wc_start and wc_start of the following pipe must
    equal valve.wc_end.
    """
    voxel_size = 0.2
    conv = _make_converter(voxel_size)
    # 7-voxel straight path along +x; valve injected at midpoint voxel (3,0,0)
    path = [(x, 0, 0) for x in range(7)]

    components = conv.convert(
        path=path,
        segment_id="seg_trim",
        nominal_diameter_m=0.08,
        valve_subtype="Gate",
    )

    valve = next(c for c in components if c["type"] == "Valve")
    valve_idx = components.index(valve)

    # Pipe immediately before the valve
    assert valve_idx > 0 and components[valve_idx - 1]["type"] == "Pipe", (
        "Expected a Pipe immediately before the Valve"
    )
    pipe_before = components[valve_idx - 1]
    assert pipe_before["wc_end"] == valve["wc_start"], (
        f"Pipe before valve: wc_end {pipe_before['wc_end']} != valve wc_start {valve['wc_start']}"
    )

    # Pipe immediately after the valve
    assert valve_idx + 1 < len(components) and components[valve_idx + 1]["type"] == "Pipe", (
        "Expected a Pipe immediately after the Valve"
    )
    pipe_after = components[valve_idx + 1]
    assert pipe_after["wc_start"] == valve["wc_end"], (
        f"Pipe after valve: wc_start {pipe_after['wc_start']} != valve wc_end {valve['wc_end']}"
    )
    print(f"  [PASS] test_valve_adjacent_pipes_trimmed_to_face  "
          f"(pipe_before.wc_end={pipe_before['wc_end']}, "
          f"valve.wc_start={valve['wc_start']}, "
          f"valve.wc_end={valve['wc_end']}, "
          f"pipe_after.wc_start={pipe_after['wc_start']})")


def test_reducer_adjacent_pipes_trimmed_to_face():
    """Pipes on either side of a Reducer must end/start at the reducer's wc_start/wc_end."""
    voxel_size = 0.2
    conv = _make_converter(voxel_size)
    path = [(x, 0, 0) for x in range(7)]
    reducer_vc = (3, 0, 0)

    components = conv.convert(
        path=path,
        segment_id="seg_reducer_trim",
        nominal_diameter_m=0.08,
        reducer_vcs={reducer_vc: {"diameter_in_m": 0.08, "diameter_out_m": 0.05}},
    )

    reducer = next(c for c in components if c["type"] == "Reducer")
    reducer_idx = components.index(reducer)

    assert reducer_idx > 0 and components[reducer_idx - 1]["type"] == "Pipe", (
        "Expected a Pipe immediately before the Reducer"
    )
    pipe_before = components[reducer_idx - 1]
    assert pipe_before["wc_end"] == reducer["wc_start"], (
        f"Pipe before reducer: wc_end {pipe_before['wc_end']} != reducer wc_start {reducer['wc_start']}"
    )

    assert reducer_idx + 1 < len(components) and components[reducer_idx + 1]["type"] == "Pipe", (
        "Expected a Pipe immediately after the Reducer"
    )
    pipe_after = components[reducer_idx + 1]
    assert pipe_after["wc_start"] == reducer["wc_end"], (
        f"Pipe after reducer: wc_start {pipe_after['wc_start']} != reducer wc_end {reducer['wc_end']}"
    )
    print(f"  [PASS] test_reducer_adjacent_pipes_trimmed_to_face  "
          f"(pipe_before.wc_end={pipe_before['wc_end']}, "
          f"reducer.wc_start={reducer['wc_start']}, "
          f"reducer.wc_end={reducer['wc_end']}, "
          f"pipe_after.wc_start={pipe_after['wc_start']})")


def test_no_spurious_elbow_before_valve():
    """Regression for Bug 10: no spurious same-axis Elbow should appear before a Valve.

    Before the fix, the normal-run loop stopped one voxel before the valve and
    emitted a spurious Elbow with axis_in == axis_out (a degenerate 0-degree
    elbow), which also truncated the preceding pipe to only 1 voxel.

    The injection design intentionally emits a 1-voxel "approach pipe" from
    path[j] to valve_vc before the Valve component.  The long pipe before that
    approach pipe must start at path[0] (not be truncated), and no Elbow with
    axis_in == axis_out must appear anywhere in the component list.

    Path: 10 voxels along +X, valve at midpoint (index 5).
    Expected component sequence: [Pipe(0→4), Pipe(4→5), Valve(5), Pipe(5→9)]
    """
    voxel_size = 0.2
    conv = _make_converter(voxel_size)
    # 10-voxel straight path along +X; valve injected at midpoint voxel (5,0,0)
    path = [(x, 0, 0) for x in range(10)]

    components = conv.convert(
        path=path,
        segment_id="seg_fullrun",
        nominal_diameter_m=0.08,
        valve_subtype="Gate",
    )

    types = [c["type"] for c in components]

    # No Elbow should have axis_in == axis_out (that would be the spurious one)
    for comp in components:
        if comp["type"] == "Elbow":
            assert comp["axis_in"] != comp["axis_out"], (
                f"Spurious elbow with axis_in == axis_out: {comp}"
            )

    valve = next(c for c in components if c["type"] == "Valve")
    valve_idx = components.index(valve)

    # The approach pipe (immediately before the valve) is always 1 voxel by design.
    # The pipe before *that* (the long run) must start at path[0] = (0,0,0),
    # not be truncated to start at path[j-1].
    # With a 10-voxel path and valve at index 5, the sequence is:
    #   Pipe(0→4) [4 hops], Pipe(4→5) [1 hop approach], Valve(5), Pipe(5→9)
    assert valve_idx >= 2, "Expected at least 2 pipes before the valve"
    long_pipe = components[valve_idx - 2]
    assert long_pipe["type"] == "Pipe", (
        f"Expected a Pipe two positions before the Valve, got {long_pipe['type']}"
    )
    vc_start = long_pipe["vc_start"]
    vc_end   = long_pipe["vc_end"]
    hops = abs(vc_end[0] - vc_start[0]) + abs(vc_end[1] - vc_start[1]) + abs(vc_end[2] - vc_start[2])
    assert hops > 1, (
        f"Long pipe before valve is only {hops} voxel(s) — expected it to span "
        f"the full run up to the approach voxel. vc_start={vc_start}, vc_end={vc_end}"
    )
    assert list(vc_start) == [0, 0, 0], (
        f"Long pipe should start at path[0]=(0,0,0), got vc_start={vc_start}"
    )

    print(f"  [PASS] test_no_spurious_elbow_before_valve  "
          f"(types={types}, long_pipe hops={hops}, "
          f"vc_start={vc_start}, vc_end={vc_end})")


# ---------------------------------------------------------------------------
# Bug 11 — InlineReducer as line endpoint (reducer at path[0] or path[-1])
# ---------------------------------------------------------------------------

def test_reducer_at_path_end():
    """Regression for Bug 11 (Case C): reducer is the last voxel of the path.

    Topology: L_001 ends at reducer_vc (reducer is to_node).
    The path for L_001 is [port_out, ..., reducer_vc].
    Before the fix, the guard ``i + 1 < len(path) - 1`` excluded injection
    when next_vc was path[-1], so the reducer was silently dropped.

    Expected component sequence: [Pipe(path[0]→reducer_vc−1), Pipe(approach), Reducer(reducer_vc)]
    i.e. the last component must be a Reducer, not a Pipe.
    """
    conv = _make_converter()
    # 5-voxel path along +X; reducer is the last voxel (4,0,0)
    path = [(x, 0, 0) for x in range(5)]
    reducer_vc = path[-1]  # (4, 0, 0)

    components = conv.convert(
        path=path,
        segment_id="seg_end_reducer",
        nominal_diameter_m=0.08,
        reducer_vcs={reducer_vc: {"diameter_in_m": 0.10, "diameter_out_m": 0.08}},
    )

    types = [c["type"] for c in components]
    assert "Reducer" in types, (
        f"Bug 11 (Case C): Reducer at path[-1] was not injected. Got types: {types}"
    )

    reducer = next(c for c in components if c["type"] == "Reducer")
    assert reducer["vc_start"] == list(reducer_vc), (
        f"Reducer vc_start should be {reducer_vc}, got {reducer['vc_start']}"
    )
    assert abs(reducer["diameter_in_m"]  - 0.10) < 1e-9
    assert abs(reducer["diameter_out_m"] - 0.08) < 1e-9

    # The last component must be the Reducer (nothing follows it in this segment)
    assert components[-1]["type"] == "Reducer", (
        f"Expected last component to be Reducer, got {components[-1]['type']}"
    )
    print(f"  [PASS] test_reducer_at_path_end  "
          f"(types={types}, reducer.vc_start={reducer['vc_start']})")


def test_reducer_at_path_start():
    """Regression for Bug 11 (Case A): reducer is the first voxel of the path.

    Topology: L_002 starts at reducer_vc (reducer is from_node).
    The path for L_002 is [reducer_vc, ..., port_in].
    Before the fix, path[0] was never checked as next_vc in the main loop,
    so the reducer was silently dropped.

    Expected component sequence: [Reducer(reducer_vc), Pipe(reducer_vc→path[-1])]
    i.e. the first component must be a Reducer.
    """
    conv = _make_converter()
    # 5-voxel path along +X; reducer is the first voxel (0,0,0)
    path = [(x, 0, 0) for x in range(5)]
    reducer_vc = path[0]  # (0, 0, 0)

    components = conv.convert(
        path=path,
        segment_id="seg_start_reducer",
        nominal_diameter_m=0.08,
        reducer_vcs={reducer_vc: {"diameter_in_m": 0.10, "diameter_out_m": 0.08}},
    )

    types = [c["type"] for c in components]
    assert "Reducer" in types, (
        f"Bug 11 (Case A): Reducer at path[0] was not injected. Got types: {types}"
    )

    reducer = next(c for c in components if c["type"] == "Reducer")
    assert reducer["vc_start"] == list(reducer_vc), (
        f"Reducer vc_start should be {reducer_vc}, got {reducer['vc_start']}"
    )
    assert abs(reducer["diameter_in_m"]  - 0.10) < 1e-9
    assert abs(reducer["diameter_out_m"] - 0.08) < 1e-9

    # The first component must be the Reducer
    assert components[0]["type"] == "Reducer", (
        f"Expected first component to be Reducer, got {components[0]['type']}"
    )
    # Must be followed by a Pipe
    assert len(components) >= 2 and components[1]["type"] == "Pipe", (
        f"Expected Pipe after Reducer, got {components[1]['type'] if len(components) > 1 else 'nothing'}"
    )
    print(f"  [PASS] test_reducer_at_path_start  "
          f"(types={types}, reducer.vc_start={reducer['vc_start']})")


# ---------------------------------------------------------------------------
# End-to-end: two-line InlineReducer model (shared endpoint)
# ---------------------------------------------------------------------------

# Two EquipmentPort nodes + one InlineReducer node.
# L_001a: port_a_out → reducer_001  (DN100)
# L_001b: reducer_001 → port_b_in   (DN50)
# The reducer voxel is a shared endpoint — it must appear in all_port_vcs
# so it is never permanently blocked, and route_context() frees it for each
# line as a normal start/goal.  Both lines must route successfully and the
# output segments must each contain a Reducer component.
TWO_LINE_REDUCER_INPUT = {
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
        {
            "id": "reducer_001",
            "type": "InlineReducer",
            "label": "DN100→DN50",
            "properties": {
                "nominal_diameter_in_mm": 100,
                "nominal_diameter_out_mm": 50,
            },
        },
    ],
    "lines": [
        {
            "id": "L_001a",
            "from_node": "port_a_out",
            "to_node": "reducer_001",
            "nominal_diameter_mm": 100,
        },
        {
            "id": "L_001b",
            "from_node": "reducer_001",
            "to_node": "port_b_in",
            "nominal_diameter_mm": 50,
        },
    ],
    "constraints": {"routing_rules": {}},
}


def test_end_to_end_two_line_reducer():
    """Full router pipeline: two-line InlineReducer model must route both lines
    and produce Reducer components in the output segments.

    Regression for the InlineReducer redesign (todos 93-99):
    - Before the fix, _reducer_blocked_voxels() added the reducer voxel to
      static_occupied, and route_context() never freed it (only start/goal
      endpoints are freed).  With via_nodes the reducer was a waypoint, not
      an endpoint, so routing always failed.
    - After the fix, InlineReducer is a shared endpoint (to_node of L_001a,
      from_node of L_001b).  Its voxel is in all_port_vcs via the normal
      from_node/to_node collection loop, so route_context() frees it for
      each line and block_path() never permanently blocks it.
    """
    gen_json = bridge.route_to_generation_json(PROJECT_ROOT, TWO_LINE_REDUCER_INPUT)

    segments = gen_json.get("segments", [])
    assert len(segments) >= 2, (
        f"Expected at least 2 segments (one per line), got {len(segments)}.  "
        f"Routing likely failed for one or both lines."
    )

    all_components = []
    for seg in segments:
        all_components.extend(seg.get("components", []))

    reducer_comps = [c for c in all_components if c.get("type") == "Reducer"]
    assert reducer_comps, (
        "Expected at least one Reducer component in generation JSON, "
        f"got component types: {[c.get('type') for c in all_components]}"
    )

    # Verify diameter fields are present on the reducer
    r = reducer_comps[0]
    assert "diameter_in_m" in r and "diameter_out_m" in r, (
        f"Reducer component missing diameter fields: {r}"
    )
    assert r["diameter_in_m"] > 0 and r["diameter_out_m"] > 0, (
        f"Reducer diameter fields must be positive: {r}"
    )

    print(
        f"  [PASS] test_end_to_end_two_line_reducer  "
        f"(segments={len(segments)}, reducers={len(reducer_comps)}, "
        f"diameter_in={r['diameter_in_m']:.4f}m, diameter_out={r['diameter_out_m']:.4f}m)"
    )


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
    test_valve_adjacent_pipes_trimmed_to_face,
    test_reducer_adjacent_pipes_trimmed_to_face,
    test_no_spurious_elbow_before_valve,
    test_reducer_at_path_end,
    test_reducer_at_path_start,
    test_end_to_end_two_line_reducer,
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
