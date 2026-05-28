from __future__ import annotations

from functools import lru_cache
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from agents.tools import get_channel_registry
from schemas.supervisor import FocusDimension
from service.collector.errors import ChannelError, ChannelNotRegisteredError
from service.desensitize import DesensitizeError
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry
from service.llm import (
    RESEARCHER_COMPRESSION_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    build_compression_fallback_user_prompt,
    build_compression_user_prompt,
    build_researcher_fallback_user_prompt,
    build_researcher_user_prompt,
)
from service.llm.client import get_llm_client
from utils.logger import get_logger

MAX_REACT_TURNS = 6
COMPRESS_AFTER_TURNS = 4
COMPRESS_AFTER_CHARS = 2400
TOOL_ACTIONS = {
    "lookup_offline_snapshot",
    "fixtures_lookup",
    "search_web",
    "fetch_url",
    "parse_page",
    "extract_structured",
    "pack_lookup",
}
ACTION_TO_CHANNEL = {
    "lookup_offline_snapshot": "lookup_offline_snapshot",
    "fixtures_lookup": "fixtures_lookup",
    "search_web": "search_web",
    "fetch_url": "fetch_url",
    "parse_page": "parse_page",
    "extract_structured": "extract_structured",
    # backward compatibility for tests and old prompt outputs
    "pack_lookup": "fixtures_lookup",
}
log = get_logger("agents.researcher_subgraph")


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
        observations_log = list(state.get("observations_log", []))

        def _has_attempt(tool_name: str) -> bool:
            for item in observations_log:
                if not isinstance(item, dict):
                    continue
                if item.get("tool") != tool_name:
                    continue
                args_raw = item.get("args", {})
                args = args_raw if isinstance(args_raw, dict) else {}
                if args.get("dimension") == dimension:
                    return True
                if tool_name in {"search_web", "fetch_url"}:
                    # online tools may not include explicit dimension argument.
                    return True
            return False

        if not _has_attempt("search_web"):
            return (
                "search_web",
                {
                    "query": f"{state['competitor_id']} {dimension} {state['research_topic']}",
                    "max_results": 5,
                },
            )
        if not _has_attempt("fetch_url"):
            return (
                "fetch_url",
                {
                    "url": _fallback_fetch_url(state=state, dimension=dimension),
                    "industry_pack_id": state["industry_pack_id"],
                    "competitor_id": state["competitor_id"],
                },
            )
        return (
            "lookup_offline_snapshot",
            {
                "industry_pack_id": state["industry_pack_id"],
                "competitor_id": state["competitor_id"],
                "dimension": dimension,
            },
        )
    return ("finalize", {"summary": "fallback finalize after pending dimensions exhausted"})


def _fallback_fetch_url(*, state: ResearcherSubState, dimension: FocusDimension) -> str:
    default_url = f"https://{state['competitor_id']}.example.com"
    try:
        pack = get_industry_pack_registry().get(state["industry_pack_id"])
    except IndustryPackNotFound:
        pack = None
    competitor = pack.competitors.get(state["competitor_id"]) if pack is not None else None
    official_url = (
        competitor.official_url.rstrip("/")
        if competitor is not None and competitor.official_url
        else default_url.rstrip("/")
    )
    if dimension == "pricing":
        return f"{official_url}/pricing"
    if dimension in {"feature", "tech_stack"}:
        return f"{official_url}/docs"
    return official_url


def _validate_lookup_action(
    *,
    action_args: dict[str, object],
    state: ResearcherSubState,
) -> tuple[str, dict[str, object]] | None:
    dimension_raw = action_args.get("dimension")
    competitor_raw = action_args.get("competitor_id")
    if (
        isinstance(dimension_raw, str)
        and dimension_raw in state.get("focus_dimensions", [])
        and isinstance(competitor_raw, str)
        and competitor_raw == state["competitor_id"]
    ):
        return (
            competitor_raw,
            {
                "industry_pack_id": state["industry_pack_id"],
                "competitor_id": competitor_raw,
                "dimension": dimension_raw,
            },
        )
    return None


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

    if action in {"pack_lookup", "lookup_offline_snapshot", "fixtures_lookup"}:
        validated = _validate_lookup_action(action_args=action_args, state=state)
        if validated is not None:
            _competitor, normalized_args = validated
            return (action, normalized_args)

    if action == "search_web":
        query_raw = action_args.get("query")
        max_results_raw = action_args.get("max_results")
        if isinstance(query_raw, str) and query_raw.strip():
            normalized_args: dict[str, object] = {"query": query_raw.strip()}
            if isinstance(max_results_raw, int):
                normalized_args["max_results"] = max_results_raw
            return ("search_web", normalized_args)

    if action == "fetch_url":
        url_raw = action_args.get("url")
        if isinstance(url_raw, str) and url_raw.strip():
            return (
                "fetch_url",
                {
                    "url": url_raw.strip(),
                    "industry_pack_id": state["industry_pack_id"],
                    "competitor_id": state["competitor_id"],
                },
            )

    if action == "parse_page":
        html_raw = action_args.get("html")
        source_url_raw = action_args.get("source_url")
        source_title_raw = action_args.get("source_title")
        if isinstance(html_raw, str) and html_raw.strip():
            normalized_args = {"html": html_raw}
            if isinstance(source_url_raw, str):
                normalized_args["source_url"] = source_url_raw
            if isinstance(source_title_raw, str):
                normalized_args["source_title"] = source_title_raw
            return ("parse_page", normalized_args)

    if action == "extract_structured":
        text_raw = action_args.get("text")
        source_url_raw = action_args.get("source_url")
        source_title_raw = action_args.get("source_title")
        if isinstance(text_raw, str) and text_raw.strip():
            normalized_args = {"text": text_raw}
            if isinstance(source_url_raw, str):
                normalized_args["source_url"] = source_url_raw
            if isinstance(source_title_raw, str):
                normalized_args["source_title"] = source_title_raw
            return ("extract_structured", normalized_args)

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
        fallback_system_prompt=RESEARCHER_SYSTEM_PROMPT,
        fallback_user_prompt=build_researcher_fallback_user_prompt(
            competitor_id=state["competitor_id"],
            pending_dimensions=list(state.get("pending_dimensions", [])),
            queried_dimensions=list(state.get("queried_dimensions", [])),
            turn_count=int(state.get("turn_count", 0)),
            max_turns=max_turns,
        ),
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
    pending_action_args = {"_action": action, **action_args}
    next_action: Literal["tool_exec", "compress", "finalize"]
    if action in TOOL_ACTIONS:
        next_action = "tool_exec"
    else:
        next_action = "finalize"

    return {
        **state,
        "llm_calls": llm_calls,
        "messages": messages,
        "pending_action_args": pending_action_args,
        "next_action": next_action,
    }


def _append_evidence_drafts(
    *,
    evidence_drafts: list[dict[str, object]],
    observation: dict[str, object],
) -> list[dict[str, object]]:
    observation_metadata_raw = observation.get("metadata", {})
    observation_metadata = (
        observation_metadata_raw if isinstance(observation_metadata_raw, dict) else {}
    )
    snippets_raw = observation.get("snippets", [])
    snippets = snippets_raw if isinstance(snippets_raw, list) else []
    dimension_raw = observation.get("dimension") or observation_metadata.get("dimension")
    competitor_id_raw = observation.get("competitor_id") or observation_metadata.get("competitor_id")
    dimension = dimension_raw if isinstance(dimension_raw, str) else "unknown"
    competitor_id = competitor_id_raw if isinstance(competitor_id_raw, str) else "unknown"

    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        quote = snippet.get("quote") or snippet.get("sanitized_text")
        sanitized_text = snippet.get("sanitized_text")
        source_url = snippet.get("source_url")
        source_title = snippet.get("source_title")
        source_type = snippet.get("source_type")
        desensitized = snippet.get("desensitized")
        metadata = snippet.get("metadata", {})
        if not isinstance(quote, str):
            continue
        if source_url is not None and not isinstance(source_url, str):
            continue
        if source_title is not None and not isinstance(source_title, str):
            continue
        if not isinstance(source_type, str):
            source_type = "article"
        if not isinstance(sanitized_text, str):
            sanitized_text = quote
        if not isinstance(metadata, dict):
            metadata = {}
        snippet_dimension_raw = metadata.get("dimension")
        snippet_competitor_raw = metadata.get("competitor_id")
        snippet_dimension = (
            snippet_dimension_raw if isinstance(snippet_dimension_raw, str) else dimension
        )
        snippet_competitor = (
            snippet_competitor_raw
            if isinstance(snippet_competitor_raw, str)
            else competitor_id
        )
        evidence_drafts.append(
            {
                "dimension": snippet_dimension,
                "competitor_id": snippet_competitor,
                "quote": quote,
                "source_url": source_url,
                "source_title": source_title,
                "source_type": source_type,
                "sanitized_text": sanitized_text,
                "desensitized": bool(desensitized),
                "metadata": metadata,
            }
        )
    return evidence_drafts


async def tool_exec(state: ResearcherSubState) -> ResearcherSubState:
    action_args = dict(state.get("pending_action_args", {}))
    action_raw = action_args.pop("_action", None)
    if not isinstance(action_raw, str):
        return {
            **state,
            "pending_action_args": {},
            "next_action": "finalize",
        }
    channel_action = ACTION_TO_CHANNEL.get(action_raw)
    if channel_action is None:
        return {
            **state,
            "pending_action_args": {},
            "next_action": "finalize",
        }
    registry = get_channel_registry()
    dimension_raw = action_args.get("dimension")
    dimension: FocusDimension | None = dimension_raw if isinstance(dimension_raw, str) else None
    try:
        observation = await registry.invoke(channel_action, args=action_args)
        observation_row = {
            "tool": action_raw,
            "args": observation.args,
            "result": observation.result.model_dump(),
        }
    except (
        ChannelError,
        ChannelNotRegisteredError,
        DesensitizeError,
        ValueError,
        TypeError,
        RuntimeError,
    ) as exc:
        observation_row = {
            "tool": action_raw,
            "args": action_args,
            "error": str(exc),
        }

    observations_log = list(state.get("observations_log", []))
    observations_log.append(observation_row)

    evidence_drafts = _append_evidence_drafts(
        evidence_drafts=list(state.get("evidence_drafts", [])),
        observation=observation_row.get("result", {}) if isinstance(observation_row, dict) else {},
    )

    if dimension is not None:
        pending_dimensions = [item for item in state.get("pending_dimensions", []) if item != dimension]
    else:
        pending_dimensions = list(state.get("pending_dimensions", []))
    queried_dimensions = list(state.get("queried_dimensions", []))
    if dimension is not None and dimension not in queried_dimensions:
        queried_dimensions.append(dimension)

    messages = list(state.get("messages", []))
    messages.append({"role": "tool", "content": str(observation_row)})
    next_turn_count = int(state.get("turn_count", 0)) + 1
    log.info(
        "researcher.tool_call",
        tool=action_raw,
        dimension=dimension,
        turn_count=next_turn_count,
        has_error="error" in observation_row,
    )

    return {
        **state,
        "turn_count": next_turn_count,
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
        fallback_system_prompt=RESEARCHER_COMPRESSION_PROMPT,
        fallback_user_prompt=build_compression_fallback_user_prompt(
            observations_log=list(state.get("observations_log", [])),
            evidence_drafts=list(state.get("evidence_drafts", [])),
        ),
    )

    llm_calls = list(state.get("llm_calls", []))
    llm_calls.append(llm_response.to_dict())

    summary_raw = llm_response.content.get("compressed_summary")
    if isinstance(summary_raw, str) and summary_raw.strip():
        summary = summary_raw.strip()
    else:
        summary = f"compressed with {len(state.get('observations_log', []))} observations"
    next_compression_count = int(state.get("compression_count", 0)) + 1
    log.info(
        "researcher.compress",
        compression_count=next_compression_count,
        observations_count=len(state.get("observations_log", [])),
        summary_len=len(summary),
    )

    return {
        **state,
        "compression_count": next_compression_count,
        "llm_calls": llm_calls,
        "messages": [
            {"role": "system", "content": "compressed researcher context"},
            {"role": "assistant", "content": summary},
        ],
        "final_summary": summary,
    }


async def finalize(state: ResearcherSubState) -> ResearcherSubState:
    if state.get("final_summary"):
        final_summary = state.get("final_summary")
        log.info(
            "researcher.finalize",
            evidence_draft_count=len(state.get("evidence_drafts", [])),
            final_summary_len=len(final_summary) if isinstance(final_summary, str) else 0,
        )
        return state

    observations = list(state.get("observations_log", []))
    final_summary = f"finalized with {len(observations)} observations"
    log.info(
        "researcher.finalize",
        evidence_draft_count=len(state.get("evidence_drafts", [])),
        final_summary_len=len(final_summary),
    )
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
