from __future__ import annotations

import time
from functools import lru_cache
import re
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from agents.tools import get_channel_registry
from schemas.contracts import validate_dimension, validate_source_type
from schemas.supervisor import FocusDimension
from service.collector.errors import ChannelError, ChannelNotRegisteredError
from service.desensitize import DesensitizeError
from service.event_bus import RunEventType, emit_run_event
from service.llm import (
    RESEARCHER_COMPRESSION_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    build_compression_fallback_user_prompt,
    build_compression_user_prompt,
    build_researcher_fallback_user_prompt,
    build_researcher_user_prompt,
)
from service.llm.client import get_llm_client
from service.skill_store import get_skill_store
from utils.logger import get_logger

MAX_REACT_TURNS = 6
COMPRESS_AFTER_TURNS = 4
COMPRESS_AFTER_CHARS = 2400
TOOL_ACTIONS = {
    "search_web",
    "fetch_url",
    "parse_page",
    "extract_structured",
    "load_skill",
    "read_skill_file",
}
ACTION_TO_CHANNEL = {
    "search_web": "search_web",
    "fetch_url": "fetch_url",
    "parse_page": "parse_page",
    "extract_structured": "extract_structured",
    "load_skill": "load_skill",
    "read_skill_file": "read_skill_file",
}
log = get_logger("agents.researcher_subgraph")

# Fields that are safe to expose in tool.start/finish event payloads.
# WHY: keep the live feed informative (query/url/skill_id) without leaking
# bulk content (raw HTML, full search results, transient sanitizer state).
_SAFE_TOOL_ARG_KEYS = ("query", "url", "max_results", "skill_id", "path")


def _safe_tool_args_summary(args: dict[str, object]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in _SAFE_TOOL_ARG_KEYS:
        if key in args and args[key] is not None:
            summary[key] = args[key]
    return summary


class ResearcherSubState(TypedDict, total=False):
    run_id: str
    research_topic: str
    competitor_id: str
    focus_dimensions: list[FocusDimension]
    pending_dimensions: list[FocusDimension]
    queried_dimensions: list[FocusDimension]
    pending_action_args: dict[str, object]
    turn_count: int
    max_turns: int
    compression_count: int
    last_compressed_turn: int
    messages: list[dict[str, str]]
    observations_log: list[dict[str, object]]
    evidence_drafts: list[dict[str, object]]
    llm_calls: list[dict[str, object]]
    next_action: Literal["tool_exec", "compress", "finalize"]
    final_summary: str
    domain_hint: str | None
    reference_urls: list[str]


def _approx_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(item.get("content", "")) for item in messages)


def _guess_skill_id(domain_hint: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", domain_hint.strip().lower()).strip("_")
    if not normalized:
        return "general_research"
    return normalized[:64]


def _has_tool_attempt(state: ResearcherSubState, tool_name: str) -> bool:
    observations_log = list(state.get("observations_log", []))
    for item in observations_log:
        if not isinstance(item, dict):
            continue
        if item.get("tool") == tool_name:
            return True
    return False


def _resolve_bootstrap_skill_id(domain_hint: str | None) -> str | None:
    store = get_skill_store()
    metadata = store.scan()
    if not metadata:
        if domain_hint is None:
            return None
        guessed = _guess_skill_id(domain_hint)
        return guessed if guessed else None

    skill_names = sorted(metadata.keys())
    if domain_hint is not None:
        guessed = _guess_skill_id(domain_hint)
        if guessed:
            for name in skill_names:
                if guessed in name or name in guessed:
                    return name
            hint_tokens = [token for token in guessed.split("_") if token]
            for token in hint_tokens:
                for name in skill_names:
                    if token in name:
                        return name

    for applies_to in ("general", "prompt_template", "source_routing"):
        names = sorted(store.list_by_applies_to(applies_to))
        if names:
            return names[0]
    return skill_names[0] if skill_names else None


def _fallback_action(state: ResearcherSubState) -> tuple[str, dict[str, object]]:
    pending_dimensions = list(state.get("pending_dimensions", []))
    if pending_dimensions:
        dimension = pending_dimensions[0]
        observations_log = list(state.get("observations_log", []))
        domain_hint_raw = state.get("domain_hint")
        domain_hint = domain_hint_raw if isinstance(domain_hint_raw, str) and domain_hint_raw.strip() else None

        def _has_attempt(tool_name: str) -> bool:
            if tool_name == "load_skill":
                return _has_tool_attempt(state, "load_skill")
            for item in observations_log:
                if not isinstance(item, dict):
                    continue
                if item.get("tool") != tool_name:
                    continue
                args_raw = item.get("args", {})
                args = args_raw if isinstance(args_raw, dict) else {}
                if args.get("dimension") == dimension:
                    return True
                if tool_name in {"search_web", "fetch_url"} and args.get("dimension") is None:
                    return True
            return False

        if domain_hint is not None and not _has_attempt("load_skill"):
            skill_id = _resolve_bootstrap_skill_id(domain_hint)
            if skill_id is not None:
                return ("load_skill", {"skill_id": skill_id})
        if not _has_attempt("search_web"):
            query_prefix = f"{domain_hint} " if domain_hint else ""
            return (
                "search_web",
                {
                    "query": f"{query_prefix}{state['competitor_id']} {dimension} {state['research_topic']}",
                    "max_results": 5,
                    "dimension": dimension,
                },
            )
        if not _has_attempt("fetch_url"):
            return (
                "fetch_url",
                {
                    "url": _fallback_fetch_url(state=state, dimension=dimension),
                    "competitor_id": state["competitor_id"],
                    "dimension": dimension,
                },
            )
        if not _has_attempt("extract_structured"):
            return (
                "extract_structured",
                {
                    "text": (
                        f"{state['competitor_id']} {dimension} signal captured for "
                        f"{state['research_topic']}."
                    ),
                    "source_title": f"{state['competitor_id']} {dimension} seed",
                    "source_type": "article",
                    "dimension": dimension,
                    "competitor_id": state["competitor_id"],
                },
            )
        return ("finalize", {"summary": "fallback finalize after online attempts exhausted"})
    return ("finalize", {"summary": "fallback finalize after pending dimensions exhausted"})


def _fallback_fetch_url(*, state: ResearcherSubState, dimension: FocusDimension) -> str:
    reference_urls_raw = state.get("reference_urls", [])
    reference_urls = (
        [item.strip() for item in reference_urls_raw if isinstance(item, str) and item.strip()]
        if isinstance(reference_urls_raw, list)
        else []
    )
    if reference_urls:
        dimension_lower = dimension.lower()
        if "pricing" in dimension_lower:
            for url in reference_urls:
                if "pricing" in url.lower() or "plan" in url.lower():
                    return url
        if "feature" in dimension_lower or "tech" in dimension_lower or "integration" in dimension_lower:
            for url in reference_urls:
                if "docs" in url.lower() or "help" in url.lower():
                    return url
        return reference_urls[0]

    default_url = f"https://{state['competitor_id']}.example.com".rstrip("/")
    if "pricing" in dimension:
        return f"{default_url}/pricing"
    if "feature" in dimension or "tech" in dimension or "integration" in dimension:
        return f"{default_url}/docs"
    return default_url


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

    if action == "search_web":
        query_raw = action_args.get("query")
        max_results_raw = action_args.get("max_results")
        if isinstance(query_raw, str) and query_raw.strip():
            normalized_args: dict[str, object] = {"query": query_raw.strip()}
            if isinstance(max_results_raw, int):
                normalized_args["max_results"] = max_results_raw
            dimension_raw = action_args.get("dimension")
            if isinstance(dimension_raw, str):
                try:
                    normalized_args["dimension"] = validate_dimension(dimension_raw)
                except ValueError:
                    pass
            return ("search_web", normalized_args)

    if action == "fetch_url":
        url_raw = action_args.get("url")
        if isinstance(url_raw, str) and url_raw.strip():
            normalized_args: dict[str, object] = {
                "url": url_raw.strip(),
                "competitor_id": state["competitor_id"],
            }
            dimension_raw = action_args.get("dimension")
            if isinstance(dimension_raw, str):
                try:
                    normalized_args["dimension"] = validate_dimension(dimension_raw)
                except ValueError:
                    pass
            return ("fetch_url", normalized_args)

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
            source_type_raw = action_args.get("source_type")
            if isinstance(source_type_raw, str):
                normalized_args["source_type"] = source_type_raw
            dimension_raw = action_args.get("dimension")
            if isinstance(dimension_raw, str):
                try:
                    normalized_args["dimension"] = validate_dimension(dimension_raw)
                except ValueError:
                    pass
            competitor_id_raw = action_args.get("competitor_id")
            if isinstance(competitor_id_raw, str) and competitor_id_raw.strip():
                normalized_args["competitor_id"] = competitor_id_raw.strip()
            else:
                normalized_args["competitor_id"] = state["competitor_id"]
            return ("extract_structured", normalized_args)

    if action == "load_skill":
        skill_id_raw = action_args.get("skill_id")
        if isinstance(skill_id_raw, str) and skill_id_raw.strip():
            return ("load_skill", {"skill_id": skill_id_raw.strip()})

    if action == "read_skill_file":
        skill_id_raw = action_args.get("skill_id")
        filename_raw = action_args.get("filename")
        if (
            isinstance(skill_id_raw, str)
            and skill_id_raw.strip()
            and isinstance(filename_raw, str)
            and filename_raw.strip()
        ):
            return (
                "read_skill_file",
                {
                    "skill_id": skill_id_raw.strip(),
                    "filename": filename_raw.strip(),
                },
            )

    return _fallback_action(state)


def _needs_compress(state: ResearcherSubState) -> bool:
    turn_count = int(state.get("turn_count", 0))
    if turn_count < COMPRESS_AFTER_TURNS:
        return False
    if int(state.get("last_compressed_turn", -1)) == turn_count:
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

    domain_hint_raw = state.get("domain_hint")
    domain_hint = domain_hint_raw if isinstance(domain_hint_raw, str) and domain_hint_raw.strip() else None
    reference_urls_raw = state.get("reference_urls", [])
    reference_urls = (
        [item for item in reference_urls_raw if isinstance(item, str)]
        if isinstance(reference_urls_raw, list)
        else []
    )

    user_prompt = build_researcher_user_prompt(
        research_topic=state["research_topic"],
        competitor_id=state["competitor_id"],
        focus_dimensions=list(state.get("focus_dimensions", [])),
        pending_dimensions=list(state.get("pending_dimensions", [])),
        queried_dimensions=list(state.get("queried_dimensions", [])),
        turn_count=int(state.get("turn_count", 0)),
        max_turns=max_turns,
        observations_log=list(state.get("observations_log", [])),
        domain_hint=domain_hint,
        reference_urls=reference_urls,
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
            domain_hint=domain_hint,
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
    if (
        domain_hint is not None
        and int(state.get("turn_count", 0)) == 0
        and action != "load_skill"
        and not _has_tool_attempt(state, "load_skill")
    ):
        bootstrap_skill_id = _resolve_bootstrap_skill_id(domain_hint)
        if bootstrap_skill_id is not None:
            action = "load_skill"
            action_args = {"skill_id": bootstrap_skill_id}
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
        else:
            try:
                source_type = validate_source_type(source_type)
            except ValueError:
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
    if isinstance(dimension_raw, str):
        try:
            dimension = validate_dimension(dimension_raw)
        except ValueError:
            dimension = None
    else:
        dimension = None

    run_id_raw = state.get("run_id")
    run_id = run_id_raw if isinstance(run_id_raw, str) else None
    competitor_id_raw = state.get("competitor_id")
    competitor_id = competitor_id_raw if isinstance(competitor_id_raw, str) else None
    turn_index = int(state.get("turn_count", 0)) + 1
    args_summary = _safe_tool_args_summary(action_args)

    if run_id is not None:
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.TOOL_START,
            payload={
                "tool": action_raw,
                "competitor_id": competitor_id,
                "dimension": dimension,
                "turn": turn_index,
                "args_summary": args_summary,
            },
        )

    tool_started_at = time.monotonic()
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
    latency_ms = int((time.monotonic() - tool_started_at) * 1000)

    if run_id is not None:
        success = "error" not in observation_row
        snippet_count = 0
        if success:
            result_section = observation_row.get("result")
            if isinstance(result_section, dict):
                snippets_section = result_section.get("snippets")
                if isinstance(snippets_section, list):
                    snippet_count = len(snippets_section)
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.TOOL_FINISH,
            payload={
                "tool": action_raw,
                "competitor_id": competitor_id,
                "dimension": dimension,
                "turn": turn_index,
                "success": success,
                "snippet_count": snippet_count,
                "latency_ms": latency_ms,
                "error": str(observation_row.get("error"))[:300] if not success else None,
            },
        )

    observations_log = list(state.get("observations_log", []))
    observations_log.append(observation_row)

    result_payload_raw = observation_row.get("result", {}) if isinstance(observation_row, dict) else {}
    if isinstance(result_payload_raw, dict):
        result_payload = {
            **result_payload_raw,
            "metadata": {
                **(
                    result_payload_raw.get("metadata", {})
                    if isinstance(result_payload_raw.get("metadata"), dict)
                    else {}
                ),
                "dimension": dimension,
                "competitor_id": state["competitor_id"],
            },
        }
    else:
        result_payload = {}

    evidence_drafts = _append_evidence_drafts(
        evidence_drafts=list(state.get("evidence_drafts", [])),
        observation=result_payload,
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
        "last_compressed_turn": int(state.get("turn_count", 0)),
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
