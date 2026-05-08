"""VLM-layer validation sub-package: JSON Schema validation with retry support."""

from .schema_validator import SchemaValidationError, validate_jsonschema

__all__ = ["validate_jsonschema", "SchemaValidationError"]
