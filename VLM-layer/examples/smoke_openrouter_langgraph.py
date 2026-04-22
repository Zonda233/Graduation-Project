"""
感知层冒烟：将本地图片 + 文本提示经 LangGraph 调用 OpenRouter（OpenAI 兼容 Chat Completions）。

依赖：见 VLM-layer/requirements-vlm-smoke.txt
配置：仓库根目录 global_config.json（API Key、端点、模型等）
提示词：VLM-layer/config/prompts.json

用法（在项目根目录）：
  pip install -r VLM-layer/requirements-vlm-smoke.txt
  python VLM-layer/examples/smoke_openrouter_langgraph.py
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "global_config.json").is_file():
            return p
    raise FileNotFoundError(
        "找不到 global_config.json：请从项目根目录运行，或保证该文件位于仓库根目录。"
    )


REPO_ROOT = _find_repo_root(Path(__file__).resolve().parents[2])
GLOBAL_CFG_PATH = REPO_ROOT / "global_config.json"
VLM_DIR = REPO_ROOT / "VLM-layer"
PROMPTS_PATH = VLM_DIR / "config" / "prompts.json"
DEFAULT_IMAGE = VLM_DIR / "examples" / "dummy" / "cyberpunk_2077.png"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _image_to_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _build_chat_model(global_cfg: dict[str, Any]) -> ChatOpenAI:
    or_cfg = global_cfg.get("openrouter") or {}
    api_key = (or_cfg.get("api_key") or "").strip() or os.environ.get(
        "OPENROUTER_API_KEY", ""
    )
    if not api_key:
        print(
            "错误：未配置 OpenRouter API Key。请在 global_config.json 的 openrouter.api_key 填写，"
            "或设置环境变量 OPENROUTER_API_KEY。",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = (or_cfg.get("base_url") or "https://openrouter.ai/api/v1").rstrip("/")
    model = or_cfg.get("chat_model") or "google/gemini-2.0-flash-001"
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
        temperature=0.2,
    )


class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def build_perception_graph(llm: ChatOpenAI) -> Any:
    def perceive(state: GraphState) -> dict[str, Any]:
        out = llm.invoke(list(state["messages"]))
        return {"messages": [out]}

    g = StateGraph(GraphState)
    g.add_node("perceive", perceive)
    g.add_edge(START, "perceive")
    g.add_edge("perceive", END)
    return g.compile()


def main() -> None:
    global_cfg = _load_json(GLOBAL_CFG_PATH)
    prompts = _load_json(PROMPTS_PATH)
    text_prompt = prompts.get("describe_image_user_prompt") or "请描述这张图片。"

    image_path = Path(os.environ.get("VLM_SMOKE_IMAGE", str(DEFAULT_IMAGE))).resolve()
    if not image_path.is_file():
        print(f"错误：找不到图片文件：{image_path}", file=sys.stderr)
        sys.exit(1)

    llm = _build_chat_model(global_cfg)
    graph = build_perception_graph(llm)

    human = HumanMessage(
        content=[
            {"type": "text", "text": text_prompt},
            {
                "type": "image_url",
                "image_url": {"url": _image_to_data_url(image_path)},
            },
        ]
    )

    result = graph.invoke({"messages": [human]})
    messages = list(result["messages"])
    last = messages[-1]
    if isinstance(last, AIMessage):
        print(last.content)
        # OpenRouter 部分模型会附带 reasoning_details；LangChain 可能放在 additional_kwargs
        rd = (last.additional_kwargs or {}).get("reasoning_details")
        if rd is not None:
            print("\n--- reasoning_details (raw) ---\n")
            print(json.dumps(rd, ensure_ascii=False, indent=2))
    else:
        print(last)


if __name__ == "__main__":
    main()
