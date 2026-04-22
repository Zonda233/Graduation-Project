from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_schema(schema_path: Path) -> dict[str, Any]:
    with schema_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Schema is not a JSON object: {schema_path}")
    return data


def validate_jsonschema(instance: dict[str, Any], schema_path: Path) -> None:
    import jsonschema

    schema = _load_schema(schema_path)
    jsonschema.validate(instance=instance, schema=schema)

