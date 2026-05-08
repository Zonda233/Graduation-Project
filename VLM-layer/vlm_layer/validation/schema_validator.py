"""JSON Schema validation with clean error extraction for LLM retry loops.

Design notes
------------
- ``validate_jsonschema`` raises ``SchemaValidationError`` (not the raw
  ``jsonschema.ValidationError``) so callers can catch a single, stable
  exception type without importing jsonschema directly.
- ``SchemaValidationError.message`` contains *only* the human-readable
  validation message — suitable for feeding back to a VLM without leaking
  internal stack traces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaValidationError(Exception):
    """Raised when an instance fails JSON Schema validation.

    Attributes
    ----------
    message:
        The concise validation message from jsonschema (no traceback).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _load_schema(schema_path: Path) -> dict[str, Any]:
    with schema_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_jsonschema(instance: dict[str, Any], schema_path: Path) -> None:
    """Validate *instance* against the JSON Schema at *schema_path*.

    Parameters
    ----------
    instance:
        The parsed JSON object to validate.
    schema_path:
        Path to the ``.json`` schema file.

    Raises
    ------
    SchemaValidationError
        If validation fails.  ``error.message`` contains only the concise
        jsonschema error text — safe to pass back to a VLM.
    """
    import jsonschema  # lazy import — not available in Blender environment

    schema = _load_schema(schema_path)
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.exceptions.ValidationError as exc:
        raise SchemaValidationError(exc.message) from exc
