from __future__ import annotations

import json
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
from service.llm.prompts import evidence_draft_refs_for_prompt
from schemas.agent_outputs import ResearcherCompressionOutput, ResearcherDecisionOutput
from service.llm import (
    RESEARCHER_COMPRESSION_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    build_compression_fallback_user_prompt,
    build_compression_repair_user_prompt,
    build_compression_user_prompt,
    build_researcher_fallback_user_prompt,
    build_researcher_repair_user_prompt,
    build_researcher_user_prompt,
)
from service.llm.harness import complete_structured
from service.llm.response import LLMResponse
from service.skill_store import get_skill_store
from utils.logger import get_logger

MAX_REACT_TURNS = 6
COMPRESS_AFTER_TURNS = 4
COMPRESS_AFTER_CHARS = 2400
OBSERVATIONS_FULL_RETAIN = 2
TOOL_ERROR_PREVIEW_LIMIT = 200
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
    observation_briefs: list[dict[str, object]]
    evidence_drafts: list[dict[str, object]]
    llm_calls: list[dict[str, object]]
    next_action: Literal["tool_exec", "compress", "finalize"]
    final_summary: str
    compressed_summary: str
    domain_hint: str | None
    reference_urls: list[str]
    discovered_urls: list[str]


def _approx_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(item.get("content", "")) for item in messages)


def _classify_tool_error(exc: Exception) -> str:
    error_type = type(exc).__name__
    message = str(exc).lower()
    if error_type == "ConnectError" or "connecterror" in message or "connection" in message:
        return "connection"
    if isinstance(exc, ChannelNotRegisteredError):
        return "channel_not_registered"
    if isinstance(exc, DesensitizeError):
        return "desensitize"
    if isinstance(exc, ChannelError):
        return "channel"
    if isinstance(exc, (ValueError, TypeError)):
        return "validation"
    if isinstance(exc, RuntimeError):
        return "runtime"
    return "unknown"


def _tool_observation_log_fields(
    *,
    observation_row: dict[str, object],
    exc: Exception | None = None,
) -> dict[str, object]:
    if "error" in observation_row:
        error_text = str(observation_row.get("error", ""))
        error_class = _classify_tool_error(exc) if exc is not None else "unknown"
        if error_class == "unknown":
            error_class = _classify_tool_error(RuntimeError(error_text))
        return {
            "success": False,
            "error_class": error_class,
            "error_preview": error_text[:TOOL_ERROR_PREVIEW_LIMIT],
        }
    return {"success": True, "error_class": None, "error_preview": None}


def _build_observation_brief(
    *,
    tool: str,
    args: dict[str, object],
    observation_row: dict[str, object],
    dimension: str | None,
) -> dict[str, object]:
    brief: dict[str, object] = {
        "tool": tool,
        "dimension": dimension if dimension is not None else args.get("dimension"),
    }
    url_raw = args.get("url")
    if isinstance(url_raw, str) and url_raw.strip():
        brief["url"] = url_raw.strip()

    if "error" in observation_row:
        brief["error_preview"] = str(observation_row.get("error", ""))[:TOOL_ERROR_PREVIEW_LIMIT]
        return brief

    result_section = observation_row.get("result")
    if not isinstance(result_section, dict):
        return brief

    snippets_section = result_section.get("snippets")
    if not isinstance(snippets_section, list):
        return brief

    brief["snippet_count"] = len(snippets_section)
    previews: list[str] = []
    for snippet in snippets_section[:3]:
        if not isinstance(snippet, dict):
            continue
        quote_raw = snippet.get("quote") or snippet.get("sanitized_text")
        if isinstance(quote_raw, str) and quote_raw.strip():
            previews.append(quote_raw.strip()[:TOOL_ERROR_PREVIEW_LIMIT])
    if previews:
        brief["quote_preview"] = " | ".join(previews)[:TOOL_ERROR_PREVIEW_LIMIT]
    return brief


def _extract_urls_from_observation(observation_row: dict[str, object]) -> list[str]:
    result_section = observation_row.get("result")
    if not isinstance(result_section, dict):
        return []
    snippets_section = result_section.get("snippets")
    if not isinstance(snippets_section, list):
        return []
    urls: list[str] = []
    for snippet in snippets_section:
        if not isinstance(snippet, dict):
            continue
        source_url = snippet.get("source_url")
        if isinstance(source_url, str) and source_url.strip():
            urls.append(source_url.strip())
    return urls


def _merge_discovered_urls(existing: list[str], new_urls: list[str]) -> list[str]:
    merged = list(existing)
    seen = set(merged)
    for url in new_urls:
        if url not in seen:
            merged.append(url)
            seen.add(url)
    return merged


def _archive_observations_log(observations_log: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(observations_log) <= OBSERVATIONS_FULL_RETAIN:
        return observations_log
    archived: list[dict[str, object]] = []
    cutoff = len(observations_log) - OBSERVATIONS_FULL_RETAIN
    for index, item in enumerate(observations_log):
        if index < cutoff and isinstance(item, dict):
            args_raw = item.get("args", {})
            args = args_raw if isinstance(args_raw, dict) else {}
            archived.append(
                {
                    "tool": item.get("tool"),
                    "archived": True,
                    "dimension": args.get("dimension"),
                    "url": args.get("url"),
                    "snippet_count": (
                        len(item["result"]["snippets"])
                        if isinstance(item.get("result"), dict)
                        and isinstance(item["result"].get("snippets"), list)
                        else 0
                    ),
                    "error_preview": (
                        str(item.get("error"))[:TOOL_ERROR_PREVIEW_LIMIT]
                        if "error" in item
                        else None
                    ),
                }
            )
            continue
        archived.append(item)
    return archived


def _effective_prompt_size(state: ResearcherSubState) -> int:
    briefs = list(state.get("observation_briefs", []))
    compressed_summary = state.get("compressed_summary", "")
    messages = list(state.get("messages", []))
    evidence_refs = evidence_draft_refs_for_prompt(list(state.get("evidence_drafts", [])))
    size = len(compressed_summary) if isinstance(compressed_summary, str) else 0
    size += _approx_chars(messages)
    size += len(json.dumps(briefs[-6:], ensure_ascii=False))
    size += len(json.dumps(evidence_refs[-8:], ensure_ascii=False))
    return size


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
    skill_names = store.get_skill_names()
    if not skill_names:
        if domain_hint is None:
            return None
        guessed = _guess_skill_id(domain_hint)
        return guessed if guessed else None

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
            fetch_url = _fallback_fetch_url(state=state, dimension=dimension)
            if fetch_url is not None:
                return (
                    "fetch_url",
                    {
                        "url": fetch_url,
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


def _pick_url_for_dimension(urls: list[str], dimension: FocusDimension) -> str | None:
    if not urls:
        return None
    dimension_lower = dimension.lower()
    if "pricing" in dimension_lower:
        for url in urls:
            lowered = url.lower()
            if "pricing" in lowered or "plan" in lowered:
                return url
    if "feature" in dimension_lower or "tech" in dimension_lower or "integration" in dimension_lower:
        for url in urls:
            lowered = url.lower()
            if "docs" in lowered or "help" in lowered:
                return url
    return urls[0]


def _fallback_fetch_url(*, state: ResearcherSubState, dimension: FocusDimension) -> str | None:
    reference_urls_raw = state.get("reference_urls", [])
    reference_urls = (
        [item.strip() for item in reference_urls_raw if isinstance(item, str) and item.strip()]
        if isinstance(reference_urls_raw, list)
        else []
    )
    if reference_urls:
        selected = _pick_url_for_dimension(reference_urls, dimension)
        if selected is not None:
            return selected

    discovered_urls_raw = state.get("discovered_urls", [])
    discovered_urls = (
        [item.strip() for item in discovered_urls_raw if isinstance(item, str) and item.strip()]
        if isinstance(discovered_urls_raw, list)
        else []
    )
    if discovered_urls:
        return _pick_url_for_dimension(discovered_urls, dimension)
    return None


def _needs_compress(state: ResearcherSubState) -> bool:
    turn_count = int(state.get("turn_count", 0))
    if turn_count < COMPRESS_AFTER_TURNS:
        return False
    if int(state.get("last_compressed_turn", -1)) == turn_count:
        return False

    messages = list(state.get("messages", []))
    if len(messages) >= 8:
        return True
    if _effective_prompt_size(state) >= COMPRESS_AFTER_CHARS:
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
    discovered_urls_raw = state.get("discovered_urls", [])
    discovered_urls = (
        [item for item in discovered_urls_raw if isinstance(item, str)]
        if isinstance(discovered_urls_raw, list)
        else []
    )
    compressed_summary_raw = state.get("compressed_summary", "")
    compressed_summary = compressed_summary_raw if isinstance(compressed_summary_raw, str) else ""
    observation_briefs = list(state.get("observation_briefs", []))

    user_prompt = build_researcher_user_prompt(
        research_topic=state["research_topic"],
        competitor_id=state["competitor_id"],
        focus_dimensions=list(state.get("focus_dimensions", [])),
        pending_dimensions=list(state.get("pending_dimensions", [])),
        queried_dimensions=list(state.get("queried_dimensions", [])),
        turn_count=int(state.get("turn_count", 0)),
        max_turns=max_turns,
        observation_briefs=observation_briefs,
        compressed_summary=compressed_summary,
        domain_hint=domain_hint,
        reference_urls=reference_urls,
        discovered_urls=discovered_urls,
    )
    pending_dimensions = list(state.get("pending_dimensions", []))
    harness_result = await complete_structured(
        model_slot="research",
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_model=ResearcherDecisionOutput,
        parser=ResearcherDecisionOutput.parse_llm_content,
        fallback_system_prompt=RESEARCHER_SYSTEM_PROMPT,
        fallback_user_prompt=build_researcher_fallback_user_prompt(
            competitor_id=state["competitor_id"],
            pending_dimensions=pending_dimensions,
            queried_dimensions=list(state.get("queried_dimensions", [])),
            turn_count=int(state.get("turn_count", 0)),
            max_turns=max_turns,
            domain_hint=domain_hint,
        ),
        repair_user_prompt_builder=lambda errors: build_researcher_repair_user_prompt(
            validation_errors=errors,
            competitor_id=state["competitor_id"],
            pending_dimensions=pending_dimensions,
        ),
        log_event="researcher.harness.finish",
    )
    llm_response = harness_result.llm_response

    llm_calls = list(state.get("llm_calls", []))
    llm_calls.append(llm_response.to_dict())

    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": user_prompt})
    messages.append({"role": "assistant", "content": str(llm_response.content)})

    action_tuple = (
        harness_result.value.to_action_tuple(competitor_id=state["competitor_id"])
        if harness_result.value is not None
        else None
    )
    if action_tuple is not None:
        action, action_args = action_tuple
    else:
        action, action_args = _fallback_action(state)
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
    tool_exc: Exception | None = None
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
        tool_exc = exc
        observation_row = {
            "tool": action_raw,
            "args": action_args,
            "error": str(exc),
        }
    latency_ms = int((time.monotonic() - tool_started_at) * 1000)
    log_fields = _tool_observation_log_fields(observation_row=observation_row, exc=tool_exc)

    if run_id is not None:
        snippet_count = 0
        if log_fields["success"]:
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
                "success": log_fields["success"],
                "snippet_count": snippet_count,
                "latency_ms": latency_ms,
                "error_class": log_fields["error_class"],
                "error_preview": log_fields["error_preview"],
                "error": log_fields["error_preview"],
            },
        )

    observations_log = list(state.get("observations_log", []))
    observations_log.append(observation_row)

    observation_briefs = list(state.get("observation_briefs", []))
    observation_briefs.append(
        _build_observation_brief(
            tool=action_raw,
            args=action_args,
            observation_row=observation_row,
            dimension=dimension,
        )
    )

    discovered_urls = list(state.get("discovered_urls", []))
    if action_raw == "search_web" and "error" not in observation_row:
        discovered_urls = _merge_discovered_urls(
            discovered_urls,
            _extract_urls_from_observation(observation_row),
        )

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
        competitor_id=state.get("competitor_id"),
        turn_count=next_turn_count,
        success=log_fields["success"],
        error_class=log_fields["error_class"],
        error_preview=log_fields["error_preview"],
    )

    return {
        **state,
        "turn_count": next_turn_count,
        "observations_log": observations_log,
        "observation_briefs": observation_briefs,
        "discovered_urls": discovered_urls,
        "evidence_drafts": evidence_drafts,
        "pending_dimensions": pending_dimensions,
        "queried_dimensions": queried_dimensions,
        "messages": messages,
        "pending_action_args": {},
    }


async def compress(state: ResearcherSubState) -> ResearcherSubState:
    compressed_summary_raw = state.get("compressed_summary", "")
    prior_summary = compressed_summary_raw if isinstance(compressed_summary_raw, str) else ""
    user_prompt = build_compression_user_prompt(
        messages=list(state.get("messages", [])),
        observation_briefs=list(state.get("observation_briefs", [])),
        evidence_drafts=list(state.get("evidence_drafts", [])),
        compressed_summary=prior_summary,
    )
    observations_log = list(state.get("observations_log", []))
    harness_result = await complete_structured(
        model_slot="compression",
        system_prompt=RESEARCHER_COMPRESSION_PROMPT,
        user_prompt=user_prompt,
        output_model=ResearcherCompressionOutput,
        parser=ResearcherCompressionOutput.parse_llm_content,
        fallback_system_prompt=RESEARCHER_COMPRESSION_PROMPT,
        fallback_user_prompt=build_compression_fallback_user_prompt(
            observations_log=observations_log,
            evidence_drafts=list(state.get("evidence_drafts", [])),
        ),
        repair_user_prompt_builder=lambda errors: build_compression_repair_user_prompt(
            validation_errors=errors,
            observation_count=len(observations_log),
        ),
        log_event="researcher.compress.harness.finish",
    )
    llm_response = harness_result.llm_response

    llm_calls = list(state.get("llm_calls", []))
    llm_calls.append(llm_response.to_dict())

    if harness_result.value is not None:
        summary = harness_result.value.compressed_summary
    else:
        summary = f"compressed with {len(observations_log)} observations"
    next_compression_count = int(state.get("compression_count", 0)) + 1
    pruned_observations = _archive_observations_log(list(state.get("observations_log", [])))
    pruned_briefs = list(state.get("observation_briefs", []))[-12:]
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
        "observations_log": pruned_observations,
        "observation_briefs": pruned_briefs,
        "compressed_summary": summary,
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
