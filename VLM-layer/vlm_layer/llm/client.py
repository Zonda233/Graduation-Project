"""LLM client construction for the VLM layer.

Centralises all ChatOpenAI / OpenRouter configuration so that other
modules never need to touch API keys or model names directly.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI


def build_chat_model(
    global_cfg: dict[str, Any],
    model_override: str | None = None,
) -> ChatOpenAI:
    """Build a :class:`ChatOpenAI` instance from *global_cfg*.

    Parameters
    ----------
    global_cfg:
        Parsed ``global_config.json``.  The ``"openrouter"`` sub-dict is
        used for API key, base URL, model name, and optional reasoning flag.
    model_override:
        When provided, overrides the model name from config.

    Raises
    ------
    ValueError
        If no API key can be found in config or environment.
    """
    or_cfg: dict[str, Any] = global_cfg.get("openrouter") or {}

    api_key = (or_cfg.get("api_key") or "").strip() or os.environ.get(
        "OPENROUTER_API_KEY", ""
    )
    if not api_key:
        raise ValueError(
            "OpenRouter API key is missing. "
            "Set global_config.json openrouter.api_key "
            "or the OPENROUTER_API_KEY environment variable."
        )

    base_url: str = (
        or_cfg.get("base_url") or "https://openrouter.ai/api/v1"
    ).rstrip("/")
    model: str = (
        model_override
        or or_cfg.get("chat_model")
        or "google/gemini-2.0-flash-001"
    )
    reasoning_enabled = bool((or_cfg.get("reasoning") or {}).get("enabled"))

    default_headers: dict[str, str] = {}
    referer = (or_cfg.get("http_referer") or "").strip()
    if referer:
        default_headers["HTTP-Referer"] = referer
    title = (or_cfg.get("app_title") or "").strip()
    if title:
        default_headers["X-Title"] = title

    extra_body: dict[str, Any] = {}
    if reasoning_enabled:
        extra_body["reasoning"] = {"enabled": True}

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers or None,
        extra_body=extra_body or None,
        temperature=1,
    )
