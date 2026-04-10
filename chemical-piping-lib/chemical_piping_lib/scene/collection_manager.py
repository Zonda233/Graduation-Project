"""
collection_manager.py
=====================
Blender Collection hierarchy management for a single build.

Every build creates a root collection named::

    ChemicalPlant_<timestamp>

with three sub-collections::

    ChemicalPlant_<timestamp>
    ├─ Equipment          ← Tanks, vessels, etc.
    ├─ Piping             ← One sub-collection per segment
    │   ├─ seg_01
    │   └─ seg_02
    └─ Joints             ← Tee joints

All created collections are stored in :attr:`SceneCollections` so that
asset builders can request the correct collection without needing to know
the full hierarchy.
"""

from __future__ import annotations

import logging
from datetime import datetime

import bpy

log = logging.getLogger(__name__)


class SceneCollections:
    """
    Holds references to all Blender Collections created for one build.

    Attributes
    ----------
    root:      Root collection (``ChemicalPlant_<timestamp>``).
    equipment: Sub-collection for large equipment (Tank, Vessel, …).
    piping:    Sub-collection for piping segments.
    joints:    Sub-collection for Tee joints.
    segments:  Dict mapping ``segment_id → bpy.types.Collection``.
    """

    def __init__(
        self,
        root:      bpy.types.Collection,
        equipment: bpy.types.Collection,
        piping:    bpy.types.Collection,
        joints:    bpy.types.Collection,
    ) -> None:
        self.root      = root
        self.equipment = equipment
        self.piping    = piping
        self.joints    = joints
        self.segments: dict[str, bpy.types.Collection] = {}

    def get_or_create_segment_col(
        self, segment_id: str
    ) -> bpy.types.Collection:
        """
        Return (creating if needed) a sub-collection under ``piping``
        for the given segment.
        """
        if segment_id not in self.segments:
            col = _new_collection(segment_id, parent=self.piping)
            self.segments[segment_id] = col
            log.debug(
                "SceneCollections: created segment collection %r.", segment_id
            )
        return self.segments[segment_id]


def setup(timestamp: str | None = None) -> SceneCollections:
    """
    Create the top-level collection hierarchy for one build and return
    a :class:`SceneCollections` describing it.

    Parameters
    ----------
    timestamp:
        Optional string suffix for the root collection name.  If ``None``
        the current UTC time is used (``YYYYMMDD_HHMMSS``).

    Returns
    -------
    :class:`SceneCollections` with all four base collections populated.
    """
    if timestamp is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    root_name = f"ChemicalPlant_{timestamp}"
    root      = _new_collection(root_name, parent=bpy.context.scene.collection)
    equipment = _new_collection("Equipment", parent=root)
    piping    = _new_collection("Piping",    parent=root)
    joints    = _new_collection("Joints",    parent=root)

    log.debug("collection_manager.setup: created hierarchy under %r.", root_name)
    return SceneCollections(root, equipment, piping, joints)


def _new_collection(
    name: str,
    parent: bpy.types.Collection,
) -> bpy.types.Collection:
    """
    Create a new Blender Collection with the given *name* and link it
    as a child of *parent*.

    If a collection with this name already exists in ``bpy.data`` it is
    reused (idempotent).
    """
    existing = bpy.data.collections.get(name)
    if existing is not None:
        # Make sure it is linked to the requested parent.
        if name not in [c.name for c in parent.children]:
            parent.children.link(existing)
        return existing

    col = bpy.data.collections.new(name)
    parent.children.link(col)
    return col


def teardown(cols: SceneCollections) -> None:
    """
    Remove all collections (and their objects) created by :func:`setup`.

    Used by :func:`~api.clear_scene`.
    """
    _remove_collection_recursive(cols.root)
    log.debug("collection_manager.teardown: removed %r.", cols.root.name)


def _remove_collection_recursive(col: bpy.types.Collection) -> None:
    """Recursively remove a collection and all its objects."""
    for child in list(col.children):
        _remove_collection_recursive(child)

    for obj in list(col.objects):
        mesh = obj.data if obj.type == 'MESH' else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    bpy.data.collections.remove(col)
