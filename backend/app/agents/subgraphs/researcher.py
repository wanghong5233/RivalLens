from __future__ import annotations

from functools import lru_cache
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from agents.tools import ToolError, pack_lookup
from schemas.supervisor import FocusDimension
from service.llm import (
    RESEARCHER_COMPRESSION_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    build_compression_user_prompt,
    build_researcher_user_prompt,
)
from service.llm.client import get_llm_client

MAX_REACT_TURNS = 6
COMPRESS_AFTER_TURNS = 4
COMPRESS_AFTER_CHARS = 2400


class ResearcherSubState(TypedDict, total=False):
    run_id: str
    industry_pack_id: str
    research_topic: str
    competitor_id: str
    focus_dimensions: list[FocusDimension]
    pending_dimensions: list[FocusDimension]
    queried_dimensions: list[FocusDimension]
    pending_action_args: dict[str, object]
    turn_count: int
    max_turns: int
    compression_count: int
    messages: list[dict[str, str]]
    observations_log: list[dict[str, object]]
    evidence_drafts: list[dict[str, object]]
    llm_calls: list[dict[str, object]]
    next_action: Literal["tool_exec", "compress", "finalize"]
    final_summary: str


def _approx_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(item.get("content", "")) for item in messages)


def _fallback_action(state: ResearcherSubState) -> tuple[str, dict[str, object]]:
    pending_dimensions = list(state.get("pending_dimensions", []))
    if pending_dimensions:
        dimension = pending_dimensions[0]
        return (
            "pack_lookup",
            {"competitor_id": state["competitor_id"], "dimension": dimension},
        )
    return ("finalize", {"summary": "fallback finalize after pending dimensions exhausted"})


def _extract_action(state: ResearcherSubState) -> tuple[str, dict[str, object]]:
    llm_calls = list(state.get("llm_calls", []))
    if not llm_calls:
        return _fallback_action(state)

    latest_content = llm_calls[-1].get("content")
    if not isinstance(latest_content, dict):
        return _fallback_action(state)

    action_raw = latest_content.get("action")
    action = action_raw if isinstance(action_raw, str) else None
    action_args_raw = latest_content.get("action_args", {})
    action_args = action_args_raw if isinstance(action_args_raw, dict) else {}

    if action == "finalize":
        return ("finalize", action_args)

    if action == "pack_lookup":
        dimension_raw = action_args.get("dimension")
        competitor_raw = action_args.get("competitor_id")
        if (
            isinstance(dimension_raw, str)
            and dimension_raw in state.get("focus_dimensions", [])
            and isinstance(competitor_raw, str)
            and competitor_raw == state["competitor_id"]
        ):
            return ("pack_lookup", action_args)

    return _fallback_action(state)


def _needs_compress(state: ResearcherSubState) -> bool:
    turn_count = int(state.get("turn_count", 0))
    if turn_count < COMPRESS_AFTER_TURNS:
        return False

    messages = list(state.get("messages", []))
    if len(messages) >= 8:
        return True
    return _approx_chars(messages) >= COMPRESS_AFTER_CHARS


async def llm_decide(state: ResearcherSubState) -> ResearcherSubState:
    max_turns = int(state.get("max_turns", MAX_REACT_TURNS))
    if int(state.get("turn_count", 0)) >= max_turns:
        return {
            **state,
            "pending_action_args": {"summary": "max researcher turns hit, force finalize"},
            "next_action": "finalize",
        }

    if _needs_compress(state):
        return {
            **state,
            "next_action": "compress",
        }

    user_prompt = build_researcher_user_prompt(
        research_topic=state["research_topic"],
        competitor_id=state["competitor_id"],
        focus_dimensions=list(state.get("focus_dimensions", [])),
        pending_dimensions=list(state.get("pending_dimensions", [])),
        queried_dimensions=list(state.get("queried_dimensions", [])),
        turn_count=int(state.get("turn_count", 0)),
        max_turns=max_turns,
        observations_log=list(state.get("observations_log", [])),
    )
    llm_response = await get_llm_client().complete_json(
        model_slot="research",
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    llm_calls = list(state.get("llm_calls", []))
    llm_calls.append(llm_response.to_dict())

    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": user_prompt})
    messages.append({"role": "assistant", "content": str(llm_response.content)})

    action, action_args = _extract_action(
        {
            **state,
            "llm_calls": llm_calls,
        }
    )
    next_action: Literal["tool_exec", "compress", "finalize"]
    if action == "pack_lookup":
        next_action = "tool_exec"
    else:
        next_action = "finalize"

    return {
        **state,
        "llm_calls": llm_calls,
        "messages": messages,
        "pending_action_args": action_args,
        "next_action": next_action,
    }


def _append_evidence_drafts(
    *,
    evidence_drafts: list[dict[str, object]],
    observation: dict[str, object],
) -> list[dict[str, object]]:
    snippets_raw = observation.get("snippets", [])
    snippets = snippets_raw if isinstance(snippets_raw, list) else []
    dimension_raw = observation.get("dimension")
    competitor_id_raw = observation.get("competitor_id")
    dimension = dimension_raw if isinstance(dimension_raw, str) else "unknown"
    competitor_id = competitor_id_raw if isinstance(competitor_id_raw, str) else "unknown"

    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        quote = snippet.get("quote")
        source_url = snippet.get("source_url")
        source_title = snippet.get("source_title")
        desensitized = snippet.get("desensitized")
        if not isinstance(quote, str) or not isinstance(source_url, str) or not isinstance(source_title, str):
            continue
        evidence_drafts.append(
            {
                "dimension": dimension,
                "competitor_id": competitor_id,
                "quote": quote,
                "source_url": source_url,
                "source_title": source_title,
                "desensitized": bool(desensitized),
            }
        )
    return evidence_drafts


async def tool_exec(state: ResearcherSubState) -> ResearcherSubState:
    action_args = dict(state.get("pending_action_args", {}))
    dimension_raw = action_args.get("dimension")
    if not isinstance(dimension_raw, str):
        return {
            **state,
            "pending_action_args": {},
            "next_action": "finalize",
        }

    dimension: FocusDimension = dimension_raw  # validated in _extract_action/fallback
    try:
        observation = pack_lookup(
            industry_pack_id=state["industry_pack_id"],
            competitor_id=state["competitor_id"],
            dimension=dimension,
        )
        observation_row = {
            "tool": observation.tool,
            "args": observation.args,
            "result": observation.result,
        }
    except ToolError as exc:
        observation_row = {
            "tool": "pack_lookup",
            "args": action_args,
            "error": str(exc),
        }

    observations_log = list(state.get("observations_log", []))
    observations_log.append(observation_row)

    evidence_drafts = _append_evidence_drafts(
        evidence_drafts=list(state.get("evidence_drafts", [])),
        observation=observation_row.get("result", {}) if isinstance(observation_row, dict) else {},
    )

    pending_dimensions = [item for item in state.get("pending_dimensions", []) if item != dimension]
    queried_dimensions = list(state.get("queried_dimensions", []))
    if dimension not in queried_dimensions:
        queried_dimensions.append(dimension)

    messages = list(state.get("messages", []))
    messages.append({"role": "tool", "content": str(observation_row)})

    return {
        **state,
        "turn_count": int(state.get("turn_count", 0)) + 1,
        "observations_log": observations_log,
        "evidence_drafts": evidence_drafts,
        "pending_dimensions": pending_dimensions,
        "queried_dimensions": queried_dimensions,
        "messages": messages,
        "pending_action_args": {},
    }


async def compress(state: ResearcherSubState) -> ResearcherSubState:
    user_prompt = build_compression_user_prompt(
        messages=list(state.get("messages", [])),
        observations_log=list(state.get("observations_log", [])),
        evidence_drafts=list(state.get("evidence_drafts", [])),
    )
    llm_response = await get_llm_client().complete_json(
        model_slot="compression",
        system_prompt=RESEARCHER_COMPRESSION_PROMPT,
        user_prompt=user_prompt,
    )

    llm_calls = list(state.get("llm_calls", []))
    llm_calls.append(llm_response.to_dict())

    summary_raw = llm_response.content.get("compressed_summary")
    if isinstance(summary_raw, str) and summary_raw.strip():
        summary = summary_raw.strip()
    else:
        summary = f"compressed with {len(state.get('observations_log', []))} observations"

    return {
        **state,
        "compression_count": int(state.get("compression_count", 0)) + 1,
        "llm_calls": llm_calls,
        "messages": [
            {"role": "system", "content": "compressed researcher context"},
            {"role": "assistant", "content": summary},
        ],
        "final_summary": summary,
    }


async def finalize(state: ResearcherSubState) -> ResearcherSubState:
    if state.get("final_summary"):
        return state

    observations = list(state.get("observations_log", []))
    final_summary = f"finalized with {len(observations)} observations"
    return {
        **state,
        "final_summary": final_summary,
    }


def _route_after_llm_decide(
    state: ResearcherSubState,
) -> Literal["tool_exec", "compress", "finalize"]:
    next_action = state.get("next_action", "finalize")
    if next_action in {"tool_exec", "compress", "finalize"}:
        return next_action
    return "finalize"


def build_researcher_subgraph():
    graph = StateGraph(ResearcherSubState)
    graph.add_node("llm_decide", llm_decide)
    graph.add_node("tool_exec", tool_exec)
    graph.add_node("compress", compress)
    graph.add_node("finalize", finalize)
    graph.set_entry_point("llm_decide")
    graph.add_conditional_edges(
        "llm_decide",
        _route_after_llm_decide,
        {
            "tool_exec": "tool_exec",
            "compress": "compress",
            "finalize": "finalize",
        },
    )
    graph.add_edge("tool_exec", "llm_decide")
    graph.add_edge("compress", "llm_decide")
    graph.add_edge("finalize", END)
    return graph.compile()


@lru_cache
def get_researcher_subgraph():
    return build_researcher_subgraph()
