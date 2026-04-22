from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import load_json
from .perception import generate_router_input_from_image
from .prompting import load_router_prompt
from .router_bridge import dump_json, route_to_generation_json
from .validation import validate_jsonschema


@dataclass
class PipelineIO:
    image_path: Path
    prompts_path: Path
    global_config_path: Path
    router_schema_path: Path
    generation_schema_path: Path
    router_input_output_path: Path
    generation_output_path: Path
    model_override: str | None = None


@dataclass
class PipelineResult:
    router_input: dict[str, Any]
    generation_json: dict[str, Any]
    vlm_raw_output: str


def run_end_to_end(repo_root: Path, io: PipelineIO, *, validate_schema: bool = True) -> PipelineResult:
    global_cfg = load_json(io.global_config_path)
    prompts_cfg = load_json(io.prompts_path)
    system_prompt = load_router_prompt(repo_root, prompts_cfg)

    router_input, raw_text = generate_router_input_from_image(
        image_path=io.image_path,
        system_prompt=system_prompt,
        global_cfg=global_cfg,
        model_override=io.model_override,
    )

    if validate_schema:
        validate_jsonschema(router_input, io.router_schema_path)

    dump_json(io.router_input_output_path, router_input)

    generation_json = route_to_generation_json(repo_root, router_input)
    if validate_schema:
        validate_jsonschema(generation_json, io.generation_schema_path)

    dump_json(io.generation_output_path, generation_json)

    return PipelineResult(
        router_input=router_input,
        generation_json=generation_json,
        vlm_raw_output=raw_text,
    )

