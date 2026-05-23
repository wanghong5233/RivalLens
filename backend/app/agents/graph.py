from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langgraph.graph import END, StateGraph

from agents.nodes.analyst import analyst_node
from agents.nodes.researcher import researcher_node
from agents.nodes.supervisor import supervisor_node
from agents.nodes.writer import writer_node
from agents.state import AgentState


def _route_after_supervisor(
    state: AgentState,
) -> Literal["researcher", "analyst", "writer", "finalize"]:
    next_action = state.get("next_action", "finalize")
    if next_action in {"researcher", "analyst", "writer", "finalize"}:
        return next_action
    return "finalize"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("writer", writer_node)
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
    graph.add_edge("writer", "supervisor")
    return graph.compile()


@lru_cache
def get_graph():
    return build_graph()
