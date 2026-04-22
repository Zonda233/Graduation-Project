from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "global_config.json").is_file():
            return path
    raise FileNotFoundError("Cannot locate repo root (missing global_config.json).")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data

