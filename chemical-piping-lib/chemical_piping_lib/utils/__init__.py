"""
utils
=====
Pure utility helpers.  No business logic, no Blender scene side-effects.

Import order guarantee
----------------------
* coords        — pure math, no bpy dependency at import time
* bmesh_utils   — requires bpy / bmesh at runtime
* ops_wrapper   — requires bpy at runtime
* material_utils— requires bpy at runtime
* boolean_utils — requires bpy at runtime
"""
