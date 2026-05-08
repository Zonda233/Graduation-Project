"""P&ID image parsing via VLM.

This module owns the full perception pipeline for a single image:
  1. Encode the image as a data-URL.
  2. Build the LangGraph perception graph.
  3. Invoke the graph with the system prompt + image message.
  4. Extract and return the JSON object from the raw model output.

The retry / validation loop lives in ``pipeline.py`` — this module is
intentionally stateless and side-effect-free (no file I/O, no logging).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ..llm.client import build_chat_model
from ..llm.graph import build_perception_graph


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _image_to_data_url(image_path: Path) -> str:
    """Encode *image_path* as a ``data:<mime>;base64,<b64>`` URL string."""
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from *raw* model output.

    Tries three strategies in order:
    1. Direct ``json.loads`` of the stripped text.
    2. Markdown fenced block extraction (````json ... ````).
    3. Balanced-brace scan to find the first complete ``{...}`` object.

    Raises
    ------
    ValueError
        If no valid JSON object can be found or parsed.
    """
    raw_text = raw.strip()

    # 1) Direct parse
    try:
        obj = json.loads(raw_text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2) Markdown fenced block
    fenced_matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, flags=re.S)
    for candidate in fenced_matches:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    # 3) Balanced-brace scan
    start = raw_text.find("{")
    if start == -1:
        raise ValueError("Model output does not contain a JSON object.")

    depth = 0
    in_str = False
    escape = False
    end = -1
    for i, ch in enumerate(raw_text[start:], start=start):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError("Cannot find a balanced JSON object in model output.")

    candidate = raw_text[start:end]
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError("Parsed JSON is not an object.")
    return obj


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_router_input_from_image(
    *,
    image_path: Path,
    system_prompt: str,
    global_cfg: dict[str, Any],
    model_override: str | None = None,
    correction_message: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Call the VLM to parse a P&ID image into a ``router_input_v1`` JSON.

    Parameters
    ----------
    image_path:
        Path to the P&ID image file.
    system_prompt:
        The full system prompt text (loaded from ``router_input_prompt.md``).
    global_cfg:
        Parsed ``global_config.json``.
    model_override:
        Optional model name override.
    correction_message:
        When provided, appended as an additional ``HumanMessage`` after the
        image message.  Used by the retry loop to feed schema validation
        errors back to the VLM.

    Returns
    -------
    tuple[dict, str]
        ``(parsed_json, raw_model_text)``
    """
    llm = build_chat_model(global_cfg, model_override=model_override)
    graph = build_perception_graph(llm)

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=[
                {"type": "text", "text": "请严格按系统要求输出 router_input_v1 JSON。"},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}},
            ]
        ),
    ]

    if correction_message:
        messages.append(HumanMessage(content=correction_message))

    result = graph.invoke({"messages": messages})
    out_messages = list(result["messages"])
    last = out_messages[-1]
    if not isinstance(last, AIMessage):
        raise ValueError("Unexpected model response type.")

    if isinstance(last.content, str):
        raw_text = last.content
    elif isinstance(last.content, list):
        text_parts: list[str] = [
            str(part.get("text", "")) if isinstance(part, dict) and part.get("type") == "text"
            else str(part)
            for part in last.content
        ]
        raw_text = "\n".join(p for p in text_parts if p).strip()
    else:
        raw_text = str(last.content)

    parsed = _extract_json_object(raw_text)
    return parsed, raw_text
