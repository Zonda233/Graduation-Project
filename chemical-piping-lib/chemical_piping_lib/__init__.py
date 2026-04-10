"""
chemical_piping_lib
===================
Blender 4.5 bpy asset library for procedural chemical plant 3D modeling.

Public API::

    from chemical_piping_lib.api import build_from_json, build_from_file, clear_scene
"""

__version__ = "1.0.0"
__author__  = "chemical-piping-lib contributors"

# Expose the top-level API so callers can do:
#   from chemical_piping_lib import build_from_json
from .api import build_from_json, build_from_file, clear_scene  # noqa: F401
