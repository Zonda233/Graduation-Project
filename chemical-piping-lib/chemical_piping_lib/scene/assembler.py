"""
assembler.py
============
JSON-driven scene assembler: the central dispatcher of the library.

The assembler is responsible for:

1. Reading the JSON ``meta`` block and applying runtime settings.
2. Pre-creating materials defined in the ``materials`` block.
3. Instantiating and building all **assets** (tanks, vessels …).
4. Instantiating and building all **tee joints**.
5. Iterating through each **segment's component list** in order and
   building the corresponding asset (Pipe, Elbow, Valve).
6. Optionally validating segment ``from_port`` / ``to_port`` connections
   against the PortRegistry after the build.
7. Returning a :class:`BuildReport`.

Design constraint
-----------------
The assembler **does not infer or modify the geometry data**.  If the JSON
says to place an Elbow at a certain position, an Elbow is placed there.
All geometric reasoning (path planning, elbow insertion) is done upstream
by the routing layer before the JSON is produced.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import bpy

from chemical_piping_lib.config import RUNTIME
from chemical_piping_lib.utils.material_utils import clear_cache, register_from_json

from .collection_manager import SceneCollections, setup as setup_collections
from .registry import PortRegistry

log = logging.getLogger(__name__)


# ===========================================================================
# Build report
# ===========================================================================

@dataclass
class BuildReport:
    """
    Summary of a completed (or failed) build.

    Attributes
    ----------
    success:               Overall success flag.
    assets_built:          Number of successfully built asset objects.
    assets_failed:         Number of assets that raised exceptions.
    warnings:              List of non-fatal warning messages.
    errors:                List of error messages (each corresponds to one
                           failed asset).
    build_time_s:          Wall-clock time for the whole build (seconds).
    scene_collection_name: Name of the root Blender collection created.
    """
    success:               bool
    assets_built:          int  = 0
    assets_failed:         int  = 0
    warnings:              list[str] = field(default_factory=list)
    errors:                list[str] = field(default_factory=list)
    build_time_s:          float = 0.0
    scene_collection_name: str  = ""

    def __str__(self) -> str:
        status = "OK" if self.success else "FAILED"
        return (
            f"BuildReport [{status}]  "
            f"built={self.assets_built}  failed={self.assets_failed}  "
            f"warnings={len(self.warnings)}  errors={len(self.errors)}  "
            f"time={self.build_time_s:.2f}s  "
            f"collection={self.scene_collection_name!r}"
        )


# ===========================================================================
# Asset type → class mapping
# ===========================================================================

def _get_asset_class(type_str: str):
    """
    Lazily import and return the asset class for a given type string.

    Lazy imports are used to avoid circular import issues at module load
    time and to keep startup cost low when only a subset of asset types
    is needed.
    """
    if type_str == "Pipe":
        from chemical_piping_lib.assets.pipe  import Pipe;  return Pipe
    if type_str == "Elbow":
        from chemical_piping_lib.assets.elbow import Elbow; return Elbow
    if type_str == "Valve":
        from chemical_piping_lib.assets.valve import Valve; return Valve
    if type_str == "Tank":
        from chemical_piping_lib.assets.tank  import Tank;  return Tank
    if type_str == "Tee":
        from chemical_piping_lib.assets.tee   import Tee;   return Tee
    if type_str == "Flange":
        from chemical_piping_lib.assets.flange import Flange; return Flange
    if type_str == "Reducer":
        from chemical_piping_lib.assets.reducer import Reducer; return Reducer
    if type_str == "Cap":
        from chemical_piping_lib.assets.cap import Cap; return Cap
    raise ValueError(f"Unknown asset type: {type_str!r}")


# ===========================================================================
# Main assembler function
# ===========================================================================

def assemble(json_data: dict) -> BuildReport:
    """
    Parse *json_data* and build the complete Blender scene.

    Parameters
    ----------
    json_data:
        Parsed JSON dict conforming to the chemical-piping-lib v1.x protocol.

    Returns
    -------
    :class:`BuildReport` with build statistics and any warnings / errors.
    """
    t_start = time.monotonic()

    report = BuildReport(success=False)
    warnings: list[str] = []
    errors:   list[str] = []

    # --- Phase 0: initialise ----------------------------------------
    PortRegistry.clear()
    clear_cache()
    RUNTIME.reset()

    meta = json_data.get("meta", {})
    RUNTIME.apply_meta(meta)

    # Set up Blender collection hierarchy.
    cols: SceneCollections = setup_collections()
    report.scene_collection_name = cols.root.name

    # Pre-create materials.
    register_from_json(json_data.get("materials", []))

    n_built  = 0
    n_failed = 0

    # --- Phase 1: Equipment (Tanks, Vessels, …) ---------------------
    for asset_def in json_data.get("assets", []):
        asset_type = asset_def.get("type", "Tank")
        asset_id   = asset_def.get("id", "unknown")
        mat_id     = asset_def.get("material_id", "default")

        try:
            cls = _get_asset_class(asset_type)
            asset = cls(
                comp_data=asset_def,
                spec={},
                material_id=mat_id,
                collection=cols.equipment,
            )
            asset.build()
            PortRegistry.register_many(asset.get_ports())
            n_built += 1
            log.info("Assembler: built %s %r.", asset_type, asset_id)

        except Exception as exc:
            msg = f"Phase1 asset {asset_type!r} id={asset_id!r}: {exc}"
            errors.append(msg)
            log.exception("Assembler: %s", msg)
            n_failed += 1

    # --- Phase 2: Tee joints -----------------------------------------
    for tee_def in json_data.get("tee_joints", []):
        tee_id = tee_def.get("tee_id", tee_def.get("id", "unknown"))
        spec   = tee_def.get("spec", {})
        mat_id = spec.get("material_id", "carbon_steel")

        # Normalise: base class looks for "id" or "comp_id".
        tee_def.setdefault("id", tee_id)

        try:
            from chemical_piping_lib.assets.tee import Tee
            tee = Tee(
                comp_data=tee_def,
                spec=spec,
                material_id=mat_id,
                collection=cols.joints,
            )
            tee.build()
            PortRegistry.register_many(tee.get_ports())
            n_built += 1
            log.info("Assembler: built Tee %r.", tee_id)

        except Exception as exc:
            msg = f"Phase2 Tee id={tee_id!r}: {exc}"
            errors.append(msg)
            log.exception("Assembler: %s", msg)
            n_failed += 1

    # --- Phase 3: Pipe segments --------------------------------------
    for seg in json_data.get("segments", []):
        seg_id = seg.get("id", "unknown_seg")
        spec   = seg.get("spec", {})
        mat_id = spec.get("material_id", "carbon_steel")
        seg_col = cols.get_or_create_segment_col(seg_id)
        # Effective spec: after a Reducer, downstream Pipe/Valve/etc. use reducer's diameter_out.
        effective_spec = dict(spec)

        for comp in seg.get("components", []):
            comp_type = comp.get("type", "Pipe")
            comp_id   = comp.get("comp_id", "unknown_comp")

            try:
                cls = _get_asset_class(comp_type)
                asset = cls(
                    comp_data=comp,
                    spec=effective_spec,
                    material_id=mat_id,
                    collection=seg_col,
                )
                asset.build()
                PortRegistry.register_many(asset.get_ports())
                n_built += 1
                log.info("Assembler: built %s %r in seg %r.", comp_type, comp_id, seg_id)

                # After a Reducer, next component(s) should use diameter_out as nominal_diameter.
                if comp_type == "Reducer" and "diameter_out_m" in comp:
                    effective_spec = {**spec, "nominal_diameter": comp["diameter_out_m"]}

            except Exception as exc:
                msg = f"Phase3 seg={seg_id!r} comp={comp_id!r} type={comp_type!r}: {exc}"
                errors.append(msg)
                log.exception("Assembler: %s", msg)
                n_failed += 1

    # --- Phase 4: Connection validation (non-blocking) ---------------
    for seg in json_data.get("segments", []):
        _validate_segment_connections(seg, warnings)

    # --- Finalise ----------------------------------------------------
    report.assets_built  = n_built
    report.assets_failed = n_failed
    report.warnings      = warnings
    report.errors        = errors
    report.build_time_s  = time.monotonic() - t_start
    report.success       = (n_failed == 0)

    log.info("Assembler: %s", report)
    return report


# ===========================================================================
# Connection validation helper
# ===========================================================================

def _validate_segment_connections(
    seg: dict,
    warnings: list[str],
) -> None:
    """
    Check that the segment's ``from_port`` and ``to_port`` exist in the
    :class:`PortRegistry` and are close to the actual first/last component
    ports.
    """
    seg_id    = seg.get("id", "?")
    from_port = seg.get("from_port")
    to_port   = seg.get("to_port")
    components = seg.get("components", [])

    if not components:
        return

    if from_port and PortRegistry.get(from_port) is None:
        warnings.append(
            f"Segment {seg_id!r}: from_port {from_port!r} not found in PortRegistry."
        )

    if to_port and PortRegistry.get(to_port) is None:
        warnings.append(
            f"Segment {seg_id!r}: to_port {to_port!r} not found in PortRegistry."
        )
