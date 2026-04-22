from __future__ import annotations

from pathlib import Path
from typing import Any


def load_router_prompt(repo_root: Path, prompts_cfg: dict[str, Any]) -> str:
    prompt_file = prompts_cfg.get("router_input_prompt_file")
    if not prompt_file:
        raise ValueError("Missing 'router_input_prompt_file' in VLM-layer/config/prompts.json")

    prompt_path = (repo_root / str(prompt_file)).resolve()
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")

