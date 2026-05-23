from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from agents.nodes.analyst import analyst_node
from agents.nodes.qa import qa_node
from agents.nodes.researcher import researcher_node
from agents.nodes.skill_curator import skill_curator_node
from agents.nodes.supervisor import supervisor_node
from agents.nodes.writer import writer_node
from agents.state import AgentState


def _route_after_supervisor(
    state: AgentState,
) -> list[Send] | Literal["researcher", "analyst", "writer", "finalize"]:
    next_action = state.get("next_action", "finalize")
    if next_action != "researcher":
        if next_action in {"analyst", "writer", "finalize"}:
            return next_action
        return "finalize"

    pending_tool_args = state.get("pending_tool_args")
    topics = pending_tool_args.get("topics") if isinstance(pending_tool_args, dict) else None
    if not isinstance(topics, list) or len(topics) <= 1:
        return "researcher"

    run_id = state.get("run_id")
    industry_pack = state.get("industry_pack")
    if run_id is None or industry_pack is None:
        return "researcher"

    sends: list[Send] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        sends.append(
            Send(
                "researcher",
                {
                    "run_id": run_id,
                    "industry_pack": industry_pack,
                    "pending_tool_args": topic,
                },
            )
        )
    if sends:
        return sends
    return "researcher"


def _route_after_qa(state: AgentState) -> Literal["supervisor", "skill_curator"]:
    qa_outcome = state.get("qa_outcome")
    if qa_outcome == "approved":
        return "skill_curator"
    return "supervisor"


def build_graph_uncompiled() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("writer", writer_node)
    graph.add_node("qa", qa_node)
    graph.add_node("skill_curator", skill_curator_node)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "researcher": "researcher",
            "analyst": "analyst",
            "writer": "writer",
            "finalize": END,
        },
    )
    graph.add_edge("researcher", "supervisor")
    graph.add_edge("analyst", "supervisor")
    graph.add_edge("writer", "qa")
    graph.add_conditional_edges(
        "qa",
        _route_after_qa,
        {
            "supervisor": "supervisor",
            "skill_curator": "skill_curator",
        },
    )
    graph.add_edge("skill_curator", END)
    return graph


def compile_graph(*, checkpointer: Any | None = None):
    graph = build_graph_uncompiled()
    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)
