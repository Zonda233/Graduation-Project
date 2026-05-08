"""Prompt loading and configuration helpers for the VLM layer.

Extracted from the old ``prompting.py`` module so that config concerns
live in their own sub-package, mirroring the chemical-piping-lib style.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_router_prompt(repo_root: Path, prompts_cfg: dict[str, Any]) -> str:
    """Load the router-input system prompt from disk.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root (used to resolve relative paths
        stored in *prompts_cfg*).
    prompts_cfg:
        Parsed ``prompts.json`` configuration dict.  Must contain a
        ``"router_input_prompt"`` key whose value is a path relative to
        *repo_root*.

    Returns
    -------
    str
        The full prompt text.
    """
    rel = prompts_cfg.get("router_input_prompt_file", "")
    if not rel:
        raise KeyError("prompts_cfg is missing key 'router_input_prompt_file'")
    prompt_path = repo_root / rel
    return prompt_path.read_text(encoding="utf-8")
