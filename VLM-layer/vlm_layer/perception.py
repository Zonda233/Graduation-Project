from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def _image_to_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _build_chat_model(global_cfg: dict[str, Any], model_override: str | None = None) -> ChatOpenAI:
    or_cfg = global_cfg.get("openrouter") or {}
    api_key = (or_cfg.get("api_key") or "").strip() or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError(
            "OpenRouter API key is missing. Set global_config.json.openrouter.api_key "
            "or environment variable OPENROUTER_API_KEY."
        )

    base_url = (or_cfg.get("base_url") or "https://openrouter.ai/api/v1").rstrip("/")
    model = model_override or or_cfg.get("chat_model") or "google/gemini-2.0-flash-001"
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
        temperature=0,
    )


def _build_graph(llm: ChatOpenAI) -> Any:
    def perceive(state: GraphState) -> dict[str, Any]:
        out = llm.invoke(list(state["messages"]))
        return {"messages": [out]}

    graph = StateGraph(GraphState)
    graph.add_node("perceive", perceive)
    graph.add_edge(START, "perceive")
    graph.add_edge("perceive", END)
    return graph.compile()


def _extract_json_object(raw: str) -> dict[str, Any]:
    # 1) Direct JSON parse
    raw_text = raw.strip()
    try:
        obj = json.loads(raw_text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2) Markdown fenced block parse
    fenced_matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, flags=re.S)
    for candidate in fenced_matches:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    # 3) First balanced object parse
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


def generate_router_input_from_image(
    *,
    image_path: Path,
    system_prompt: str,
    global_cfg: dict[str, Any],
    model_override: str | None = None,
) -> tuple[dict[str, Any], str]:
    llm = _build_chat_model(global_cfg, model_override=model_override)
    graph = _build_graph(llm)

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=[
                {"type": "text", "text": "请严格按系统要求输出 router_input_v1 JSON。"},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}},
            ]
        ),
    ]
    result = graph.invoke({"messages": messages})
    out_messages = list(result["messages"])
    last = out_messages[-1]
    if not isinstance(last, AIMessage):
        raise ValueError("Unexpected model response type.")

    if isinstance(last.content, str):
        raw_text = last.content
    elif isinstance(last.content, list):
        text_parts: list[str] = []
        for part in last.content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
            else:
                text_parts.append(str(part))
        raw_text = "\n".join(p for p in text_parts if p).strip()
    else:
        raw_text = str(last.content)

    parsed = _extract_json_object(raw_text)
    return parsed, raw_text

