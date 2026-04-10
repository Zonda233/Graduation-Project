"""
Pytest fixtures for chemical-piping-lib tests.

- Puts project root on sys.path.
- Mocks bpy and mathutils so the package can be imported outside Blender.
  Coords tests use the mocked Vector (minimal implementation sufficient for
  vc_to_wc_center / wc_to_vc / axis_to_vec).
"""

import math
import sys
from pathlib import Path

import pytest

# Project root (parent of tests/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Mock bpy (so assembler/api can be imported) ---
if "bpy" not in sys.modules:
    import types
    _bpy = types.ModuleType("bpy")
    _bpy.types = types.ModuleType("bpy.types")
    _bpy.context = types.ModuleType("bpy.context")
    sys.modules["bpy"] = _bpy
    sys.modules["bpy.types"] = _bpy.types
    sys.modules["bpy.context"] = _bpy.context

# --- Mock mathutils (so registry + coords can be imported; coords tests need Vector) ---
if "mathutils" not in sys.modules:
    import types

    class _Vector:
        def __init__(self, seq=(0, 0, 0)):
            if len(seq) >= 3:
                self.x, self.y, self.z = float(seq[0]), float(seq[1]), float(seq[2])
            else:
                self.x = self.y = self.z = 0.0

        @property
        def length(self):
            return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

        def normalized(self):
            L = self.length
            if L < 1e-10:
                return _Vector((1, 0, 0))
            return _Vector((self.x / L, self.y / L, self.z / L))

        def copy(self):
            return _Vector((self.x, self.y, self.z))

        def __iter__(self):
            return iter((self.x, self.y, self.z))

    class _Quaternion:
        def __init__(self, seq=(1, 0, 0, 0)):
            pass

    class _Matrix:
        def __init__(self, *args):
            pass

    _mathutils = types.ModuleType("mathutils")
    _mathutils.Vector = _Vector
    _mathutils.Quaternion = _Quaternion
    _mathutils.Matrix = _Matrix
    sys.modules["mathutils"] = _mathutils


@pytest.fixture(autouse=True)
def reset_runtime():
    """Reset config.RUNTIME to defaults before/after each test."""
    from chemical_piping_lib.config import RUNTIME
    RUNTIME.reset()
    yield
    RUNTIME.reset()
