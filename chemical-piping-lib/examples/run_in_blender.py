"""
run_in_blender.py
=================
Blender runner script for the chemical-piping-lib integration test.

Usage (interactive Blender)
---------------------------
1. Open Blender 4.5.
2. Go to the **Scripting** workspace.
3. Open this file.
4. Edit ``LIB_ROOT`` and ``JSON_FILE`` to match your paths.
5. Click **Run Script**.

Usage (headless)
----------------
.. code-block:: bash

    blender --background --python examples/run_in_blender.py

(Set ``LIB_ROOT`` and ``JSON_FILE`` environment variables or edit below.)
"""

import os
import sys
import logging

# ---------------------------------------------------------------------------
# Configuration — edit these two paths
# ---------------------------------------------------------------------------

# Absolute path to the repository root (the folder containing
# 'chemical_piping_lib/').
LIB_ROOT  = os.environ.get(
    "CPL_LIB_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

# Path to the JSON scene file to build.
# Default: full_components_scene.json (covers Tank, Pipe, Elbow, Tee, Valve, Reducer, Cap).
JSON_FILE = os.environ.get(
    "CPL_JSON_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_components_scene.json"),
)

# ---------------------------------------------------------------------------
# Bootstrap: add the repo root to sys.path so the library is importable.
# ---------------------------------------------------------------------------

if LIB_ROOT not in sys.path:
    sys.path.insert(0, LIB_ROOT)

# ---------------------------------------------------------------------------
# Logging setup: print INFO+ to stdout so we can follow the build progress.
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

# ---------------------------------------------------------------------------
# Run the build
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"  chemical-piping-lib  —  integration test")
print(f"  lib  : {LIB_ROOT}")
print(f"  scene: {JSON_FILE}")
print(f"{'='*60}\n")

from chemical_piping_lib.api import build_from_file   # noqa: E402  (after sys.path setup)

report = build_from_file(JSON_FILE)

print(f"\n{'='*60}")
print(f"  BUILD RESULT: {'SUCCESS' if report.success else 'FAILED'}")
print(f"  Assets built : {report.assets_built}")
print(f"  Assets failed: {report.assets_failed}")
print(f"  Warnings     : {len(report.warnings)}")
print(f"  Errors       : {len(report.errors)}")
print(f"  Time         : {report.build_time_s:.2f} s")
print(f"  Collection   : {report.scene_collection_name}")

if report.warnings:
    print("\n  WARNINGS:")
    for w in report.warnings:
        print(f"    ⚠  {w}")

if report.errors:
    print("\n  ERRORS:")
    for e in report.errors:
        print(f"    ✗  {e}")

print(f"{'='*60}\n")
