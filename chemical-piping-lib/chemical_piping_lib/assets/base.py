"""
base.py
=======
Abstract base class for all chemical-piping-lib asset types.

Every concrete asset (Pipe, Elbow, Tee, …) inherits from
:class:`PipingAsset` and must implement:

* :meth:`build` — create and return the ``bpy.types.Object``.
* :meth:`get_ports` — return a ``{port_name: Vector}`` mapping of the
  world-space connection points exposed by this asset.

Lifecycle
---------
::

    asset = Pipe(comp_data, spec, material_id)   # __init__: validate + store
    obj   = asset.build()                        # geometry created in Blender
    ports = asset.get_ports()                    # query connection points

After :meth:`build` the ``asset.obj`` property is available.  Accessing it
before :meth:`build` raises ``RuntimeError``.

Thread safety
-------------
Blender's Python API is single-threaded.  These classes make no attempt at
concurrency and should only be used from the main Blender Python thread.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import bpy
    from mathutils import Vector

from chemical_piping_lib.utils.material_utils import assign_material

log = logging.getLogger(__name__)


class PipingAsset(ABC):
    """
    Abstract base for all chemical-piping-lib asset classes.

    Parameters
    ----------
    comp_data:
        The component dictionary taken directly from the JSON input.
        At minimum it must contain ``"comp_id"`` (or ``"id"`` for top-level
        assets such as Tank).
    spec:
        The ``spec`` dict of the parent segment (or an equivalent dict for
        top-level assets).  Used to obtain shared properties like
        ``nominal_diameter``, ``material_id``, and ``with_flanges``.
    material_id:
        The material identifier string (key into
        :data:`config.MATERIAL_PRESETS` or a JSON-registered material id).
        If omitted (empty string), falls back to ``"default"``.
    collection:
        Optional ``bpy.types.Collection`` to link the built object into.
        If ``None``, the object is linked to the scene's root collection.
    """

    def __init__(
        self,
        comp_data:   dict,
        spec:        dict,
        material_id: str,
        collection=None,   # bpy.types.Collection | None
    ) -> None:
        # Resolve comp_id: top-level assets use "id", components use "comp_id".
        self.comp_id: str = (
            comp_data.get("comp_id")
            or comp_data.get("id")
            or "unknown"
        )
        self.comp_data:   dict  = comp_data
        self.spec:        dict  = spec
        self.material_id: str   = material_id or "default"
        self.collection         = collection   # bpy.types.Collection | None

        # Set after build() is called.
        self._obj = None  # bpy.types.Object | None

        log.debug("PipingAsset.__init__: %s (%s)", self.__class__.__name__, self.comp_id)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def build(self):  # -> bpy.types.Object
        """
        Construct the 3-D geometry in Blender and return the resulting
        ``bpy.types.Object``.

        Implementations **must**:

        1. Assign the created object to ``self._obj``.
        2. Call ``self._finalise(material_id)`` at the end to apply the
           material and link the object to the correct collection.
        3. Return ``self._obj``.
        """

    @abstractmethod
    def get_ports(self) -> dict:  # -> dict[str, Vector]
        """
        Return a ``{port_name: Vector}`` mapping of world-space connection
        points for this asset.

        The port names are asset-type specific:

        * Pipe / Valve : ``{"start": ..., "end": ...}``
        * Elbow        : ``{"inlet": ..., "outlet": ...}``
        * Tee          : ``{"run_a": ..., "run_b": ..., "branch": ...}``
        * Tank         : arbitrary names matching JSON ``ports[].port_id``
        * Flange       : ``{"face": ...}``

        The method may only be called **after** :meth:`build`.
        """

    # ------------------------------------------------------------------
    # Convenience property
    # ------------------------------------------------------------------

    @property
    def obj(self):
        """The ``bpy.types.Object`` created by :meth:`build`."""
        if self._obj is None:
            raise RuntimeError(
                f"{self.__class__.__name__} '{self.comp_id}' has not been "
                "built yet.  Call build() first."
            )
        return self._obj

    # ------------------------------------------------------------------
    # Shared post-build steps
    # ------------------------------------------------------------------

    def _finalise(self, material_id: str | None = None) -> None:
        """
        Apply material and link the object to the target collection.

        Call this at the end of every :meth:`build` implementation.

        Parameters
        ----------
        material_id:
            Override the instance material id.  Useful for sub-components
            (e.g. a flange added by a Pipe) that may use a different material.
            If ``None``, uses ``self.material_id``.
        """
        if self._obj is None:
            raise RuntimeError(
                "_finalise called before self._obj was set in build()."
            )

        mid = material_id or self.material_id
        assign_material(self._obj, mid)

        if getattr(self._obj, "type", None) == "MESH" and self._obj.data is not None:
            for poly in self._obj.data.polygons:
                poly.use_smooth = True
            self._obj.data.update()

        # Link to the requested collection (if not already linked).
        if self.collection is not None:
            if self._obj.name not in self.collection.objects:
                self.collection.objects.link(self._obj)
            # Unlink from scene root collection to avoid duplicates in outliner.
            import bpy
            scene_col = bpy.context.scene.collection
            if self._obj.name in scene_col.objects:
                scene_col.objects.unlink(self._obj)

        log.debug(
            "PipingAsset._finalise: %s %r material=%r collection=%s",
            self.__class__.__name__,
            self.comp_id,
            mid,
            self.collection.name if self.collection else "<scene root>",
        )

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        built = self._obj is not None
        return (
            f"<{self.__class__.__name__} id={self.comp_id!r} built={built}>"
        )
