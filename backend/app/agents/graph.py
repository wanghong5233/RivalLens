from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from agents.nodes.supervisor import supervisor_node
from agents.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.set_entry_point("supervisor")
    graph.add_edge("supervisor", END)
    return graph.compile()


@lru_cache
def get_graph():
    return build_graph()
