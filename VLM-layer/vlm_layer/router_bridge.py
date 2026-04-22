from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_router_layer_package(router_layer_dir: Path) -> None:
    pkg_init = router_layer_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "router_layer",
        str(pkg_init),
        submodule_search_locations=[str(router_layer_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to create module spec for router_layer.")

    pkg = importlib.util.module_from_spec(spec)
    sys.modules["router_layer"] = pkg
    spec.loader.exec_module(pkg)


def route_to_generation_json(repo_root: Path, router_input: dict[str, Any]) -> dict[str, Any]:
    router_layer_dir = repo_root / "router-layer"
    if not router_layer_dir.is_dir():
        raise FileNotFoundError(f"router-layer not found: {router_layer_dir}")

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    cpl_root = repo_root / "chemical-piping-lib"
    if cpl_root.is_dir() and str(cpl_root) not in sys.path:
        sys.path.insert(0, str(cpl_root))

    _load_router_layer_package(router_layer_dir)

    from router_layer.json_emitter import SchemaCompliantJsonEmitter
    from router_layer.service import DefaultRouterService

    service = DefaultRouterService(json_emitter=SchemaCompliantJsonEmitter())
    return service.route(router_input)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(path.parent, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

