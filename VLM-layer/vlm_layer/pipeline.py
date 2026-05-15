"""End-to-end VLM pipeline with schema-validation and routing retry loop.

Pipeline stages
---------------
1. Load config & prompt.
2. Call VLM to parse P&ID image → ``router_input_v1`` JSON.
3. Validate against router-input schema.
   - On failure: log the error, feed it back to the VLM, retry (up to
     ``max_retries`` times).
4. Route through router-layer → generation JSON.
   - On ``RuntimeError`` (routing failure): log the failure report, feed it
     back to the VLM as a correction message, retry from step 2.
5. Validate against generation schema.
   - On failure: log the error, feed it back to the VLM, retry from step 2.
6. Persist both JSON files and return a ``PipelineResult``.

Design notes
------------
- Schema-validation retry messages contain only the ``SchemaValidationError.message``
  text (the concise jsonschema error), never a full Python traceback.
- Routing failure retry messages contain the full ``failure_report`` string
  produced by ``DefaultRouterService`` — it lists each unrouted line with its
  start/goal voxels and nearby occupied voxels so the VLM can adjust node
  positions or remove conflicting lines.
- Each retry attempt is logged at WARNING level so operators can monitor
  LLM correction quality.
- ``max_retries`` defaults to 3; set to 0 to disable retries entirely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import load_json
from .config import load_router_prompt
from .perception import generate_router_input_from_image
from .router_bridge import dump_json, route_to_generation_json
from .validation import SchemaValidationError, validate_jsonschema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass
class PipelineIO:
    """Paths and options for a single end-to-end pipeline run."""

    image_path: Path
    prompts_path: Path
    global_config_path: Path
    router_schema_path: Path
    generation_schema_path: Path
    router_input_output_path: Path
    generation_output_path: Path
    model_override: str | None = None
    max_retries: int = 3


@dataclass
class PipelineResult:
    """Outputs produced by a successful pipeline run."""

    router_input: dict[str, Any]
    generation_json: dict[str, Any]
    vlm_raw_output: str
    retry_count: int = field(default=0)


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------

_SCHEMA_RETRY_PREAMBLE = (
    "你上一次的输出未通过 JSON Schema 校验，错误信息如下：\n\n"
    "{error}\n\n"
    "请根据上述错误修正输出，重新生成符合要求的 router_input_v1 JSON。"
    "只输出 JSON 对象本体，不要任何额外文字。"
)

_ROUTING_RETRY_PREAMBLE = (
    "你上一次的输出在路由阶段失败，以下管线无法完成路径规划：\n\n"
    "{report}\n\n"
    "请根据上述失败信息调整节点位置或删除冲突管线，"
    "重新生成符合要求的 router_input_v1 JSON。"
    "只输出 JSON 对象本体，不要任何额外文字。"
)


def _make_schema_correction_message(error_message: str) -> str:
    return _SCHEMA_RETRY_PREAMBLE.format(error=error_message)


def _make_routing_correction_message(failure_report: str) -> str:
    return _ROUTING_RETRY_PREAMBLE.format(report=failure_report)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_end_to_end(
    repo_root: Path,
    io: PipelineIO,
    *,
    validate_schema: bool = True,
) -> PipelineResult:
    """Run the full VLM → router → generation pipeline.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.
    io:
        All I/O paths and options for this run.
    validate_schema:
        When ``False``, schema validation (and retries) are skipped entirely.
        Useful for quick smoke tests.

    Returns
    -------
    PipelineResult
        Contains both JSON payloads, the raw VLM text, and the number of
        retry attempts consumed.

    Raises
    ------
    SchemaValidationError
        If validation still fails after all retries are exhausted.
    """
    global_cfg = load_json(io.global_config_path)
    prompts_cfg = load_json(io.prompts_path)
    system_prompt = load_router_prompt(repo_root, prompts_cfg)

    correction_message: str | None = None
    retry_count = 0
    max_attempts = 1 + (io.max_retries if validate_schema else 0)

    for attempt in range(max_attempts):
        if attempt > 0:
            logger.warning(
                "VLM retry attempt %d/%d (correction: %s)",
                attempt,
                io.max_retries,
                correction_message[:120] if correction_message else "",
            )

        router_input, raw_text = generate_router_input_from_image(
            image_path=io.image_path,
            system_prompt=system_prompt,
            global_cfg=global_cfg,
            model_override=io.model_override,
            correction_message=correction_message,
        )

        if not validate_schema:
            break

        # --- validate router-input schema ---
        try:
            validate_jsonschema(router_input, io.router_schema_path)
        except SchemaValidationError as exc:
            logger.warning(
                "router_input schema validation failed (attempt %d): %s",
                attempt + 1,
                exc.message,
            )
            correction_message = _make_schema_correction_message(exc.message)
            retry_count += 1
            if attempt < max_attempts - 1:
                continue
            raise

        # --- route to generation JSON ---
        try:
            generation_json = route_to_generation_json(repo_root, router_input)
        except RuntimeError as exc:
            # route_to_generation_json raises RuntimeError whose message is the
            # full failure_report produced by DefaultRouterService.
            failure_report = str(exc)
            logger.warning(
                "routing failed (attempt %d):\n%s",
                attempt + 1,
                failure_report,
            )
            correction_message = _make_routing_correction_message(failure_report)
            retry_count += 1
            if attempt < max_attempts - 1:
                continue
            raise

        # --- validate generation schema ---
        try:
            validate_jsonschema(generation_json, io.generation_schema_path)
        except SchemaValidationError as exc:
            logger.warning(
                "generation schema validation failed (attempt %d): %s",
                attempt + 1,
                exc.message,
            )
            correction_message = _make_schema_correction_message(exc.message)
            retry_count += 1
            if attempt < max_attempts - 1:
                continue
            raise

        # Both validations passed — exit the retry loop.
        break

    else:
        # Loop exhausted without a clean break — last exception already raised.
        pass  # pragma: no cover

    # If validate_schema is False we still need generation_json
    if not validate_schema:
        generation_json = route_to_generation_json(repo_root, router_input)

    dump_json(io.router_input_output_path, router_input)
    dump_json(io.generation_output_path, generation_json)

    return PipelineResult(
        router_input=router_input,
        generation_json=generation_json,
        vlm_raw_output=raw_text,
        retry_count=retry_count,
    )
