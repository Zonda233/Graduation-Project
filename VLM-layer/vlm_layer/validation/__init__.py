"""VLM-layer validation sub-package.

Provides two layers of validation for router_input_v1 JSON:

1. JSON Schema validation (:func:`validate_jsonschema`) -- structural checks
   against the router_input_v1.json schema file.
2. Semantic validation (:func:`validate_semantics`) -- cross-reference
   integrity and simplified GB engineering rules.

Both validators raise exception types that carry a human-readable message
suitable for feeding directly into the VLM retry correction loop.
"""

from .schema_validator import SchemaValidationError, validate_jsonschema
from .semantic_validator import SemanticValidationError, validate_semantics

__all__ = [
    "validate_jsonschema",
    "SchemaValidationError",
    "validate_semantics",
    "SemanticValidationError",
]
