"""LangGraph graph builders for the VLM perception pipeline.

Keeping graph topology separate from the LLM client and from the
perception logic makes it easy to swap graph shapes (e.g. add a
self-correction node) without touching unrelated code.
"""

from __future__ import annotations

from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    """Shared state threaded through every LangGraph node."""

    messages: Annotated[Sequence[BaseMessage], add_messages]


def build_perception_graph(llm: ChatOpenAI) -> Any:
    """Build and compile a single-node perception graph.

    The graph contains one ``perceive`` node that calls *llm* with the
    current message list and appends the response.

    Parameters
    ----------
    llm:
        A configured :class:`~langchain_openai.ChatOpenAI` instance.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph ready to be invoked with
        ``{"messages": [...]}``.
    """

    def perceive(state: GraphState) -> dict[str, Any]:
        out = llm.invoke(list(state["messages"]))
        return {"messages": [out]}

    graph = StateGraph(GraphState)
    graph.add_node("perceive", perceive)
    graph.add_edge(START, "perceive")
    graph.add_edge("perceive", END)
    return graph.compile()
