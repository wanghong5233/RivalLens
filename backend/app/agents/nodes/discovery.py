from __future__ import annotations

import re
import time
from collections.abc import Sequence
from datetime import datetime, timezone

from agents.nodes.planner import reconcile_plan_tree_after_discovery
from agents.state import AgentState
from agents.state_coercion import coerce_plan_tree
from agents.tools import get_channel_registry
from core.defaults import (
    DEFAULT_DISCOVER_MAX_RESULTS,
    DISCOVERY_SEARCH_MAX_RESULTS_CAP,
    DISCOVERY_SNIPPETS_TO_EXTRACT,
    MAX_DISCOVERY_SEARCH_QUERIES,
)
from db.engine import get_session_factory
from models.run import Run
from models.step import Step
from schemas.ids import make_id
from service.collector.errors import ChannelError
from service.event_bus import RunEventType, emit_run_event
from schemas.agent_outputs import DiscoveryExtractOutput
from service.llm import (
    DISCOVERY_EXTRACT_SYSTEM_PROMPT,
    build_discovery_extract_fallback_user_prompt,
    build_discovery_extract_repair_user_prompt,
    build_discovery_extract_user_prompt,
)
from service.llm.harness import complete_structured
from utils.log_node import log_node
from utils.logger import bind_step, get_logger

log = get_logger("agents.discovery")
_DISCOVERY_SNIPPET_SAMPLE_LIMIT = 3
_DISCOVERY_SNIPPET_PREVIEW_LIMIT = 220
_DISCOVERY_EVIDENCE_PREVIEW_LIMIT = 220


def _normalize_alias_key(value: str) -> str:
    lowered = value.casefold()
    without_punctuation = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return " ".join(without_punctuation.split())


def _normalize_grounding_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _quote_is_grounded(*, evidence_quote: str, snippets: Sequence[str]) -> bool:
    normalized_quote = _normalize_grounding_text(evidence_quote)
    if not normalized_quote:
        return False
    return any(normalized_quote in _normalize_grounding_text(snippet) for snippet in snippets)


def _filter_discovery_candidates(
    *,
    candidates: Sequence[object],
    snippets: Sequence[str],
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]]]:
    discovered: list[str] = []
    filtered_out: list[dict[str, object]] = []
    relevance: list[dict[str, object]] = []
    seen_aliases: set[str] = set()

    for candidate in candidates:
        name = str(getattr(candidate, "name", "") or "").strip()
        is_competitor = bool(getattr(candidate, "is_competitor", False))
        relevance_reason = str(getattr(candidate, "relevance_reason", "") or "").strip()
        evidence_quote = str(getattr(candidate, "evidence_quote", "") or "").strip()
        alias_key = _normalize_alias_key(name)

        if not name:
            filtered_out.append({"name": "", "reason": "blank_name"})
            continue
        if not is_competitor:
            filtered_out.append({"name": name, "reason": "not_competitor"})
            continue
        if not evidence_quote:
            filtered_out.append({"name": name, "reason": "missing_evidence_quote"})
            continue
        if not _quote_is_grounded(evidence_quote=evidence_quote, snippets=snippets):
            filtered_out.append({"name": name, "reason": "grounding_miss"})
            continue
        if not alias_key:
            filtered_out.append({"name": name, "reason": "blank_alias_key"})
            continue
        if alias_key in seen_aliases:
            filtered_out.append({"name": name, "reason": "duplicate_alias"})
            continue

        seen_aliases.add(alias_key)
        discovered.append(name)
        relevance.append(
            {
                "name": name,
                "relevance_reason": relevance_reason,
                "evidence_quote_preview": evidence_quote[:_DISCOVERY_EVIDENCE_PREVIEW_LIMIT],
            }
        )

    return discovered, filtered_out, relevance


def _build_snippet_sample(*, snippet: object, query: str) -> dict[str, object] | None:
    quote = getattr(snippet, "sanitized_text", None) or getattr(snippet, "quote", None)
    if not isinstance(quote, str) or not quote.strip():
        return None
    source_title = getattr(snippet, "source_title", None)
    source_url = getattr(snippet, "source_url", None)
    source_type = getattr(snippet, "source_type", None)
    return {
        "source_title": source_title if isinstance(source_title, str) else None,
        "source_url": source_url if isinstance(source_url, str) else None,
        "source_type": source_type if isinstance(source_type, str) else None,
        "quote_preview": quote.strip()[:_DISCOVERY_SNIPPET_PREVIEW_LIMIT],
        "query": query,
    }


@log_node("discovery")
async def discovery_node(state: AgentState) -> AgentState:
    """Execute competitor discovery via web search + LLM extraction."""
    run_id = state.get("run_id", "unknown")
    pending_tool_args = state.get("pending_tool_args", {})
    user_query = state.get("user_query", "")

    search_queries: list[str] = pending_tool_args.get("search_queries", [user_query])
    domain_context: str = pending_tool_args.get("domain_context", user_query)
    max_results: int = pending_tool_args.get("max_results", DEFAULT_DISCOVER_MAX_RESULTS)

    session_factory = state.get("session_factory") or get_session_factory()

    step_id = make_id("step_")
    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="discovery",
            status="running",
            retry_count=0,
            payload={"search_queries": search_queries, "domain_context": domain_context},
        )
        session.add(step)
        await session.commit()

    registry = get_channel_registry()
    all_snippets: list[str] = []
    snippet_samples: list[dict[str, object]] = []

    for query in search_queries[:MAX_DISCOVERY_SEARCH_QUERIES]:
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.TOOL_START,
            step_id=step_id,
            payload={
                "tool": "search_web",
                "competitor_id": None,
                "dimension": None,
                "args_summary": {
                    "query": query,
                    "max_results": min(max_results, DISCOVERY_SEARCH_MAX_RESULTS_CAP),
                },
            },
        )
        tool_started_at = time.monotonic()
        snippets_added = 0
        error_text: str | None = None
        try:
            observation = await registry.invoke(
                "search_web",
                args={
                    "query": query,
                    "max_results": min(max_results, DISCOVERY_SEARCH_MAX_RESULTS_CAP),
                },
            )
            for snippet in observation.result.snippets:
                text = snippet.sanitized_text or snippet.quote
                if text:
                    all_snippets.append(text[:500])
                    snippets_added += 1
                    if len(snippet_samples) < _DISCOVERY_SNIPPET_SAMPLE_LIMIT:
                        sample = _build_snippet_sample(snippet=snippet, query=query)
                        if sample is not None:
                            snippet_samples.append(sample)
        except ChannelError as exc:
            # Channel boundary contract: every recoverable failure inside the
            # search channel (rate-limit, timeout, auth, no-snippet) is
            # surfaced as ChannelError. Anything else (asyncio.CancelledError,
            # KeyError from a bug, etc.) must propagate so node.error fires.
            error_text = f"{type(exc).__name__}: {exc}"
            with bind_step(step_id):
                log.warning(
                    "discovery.search_failed",
                    query=query,
                    error_type=type(exc).__name__,
                    error=str(exc)[:300],
                )
        latency_ms = int((time.monotonic() - tool_started_at) * 1000)
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.TOOL_FINISH,
            step_id=step_id,
            payload={
                "tool": "search_web",
                "competitor_id": None,
                "dimension": None,
                "success": error_text is None,
                "snippet_count": snippets_added,
                "latency_ms": latency_ms,
                "error": error_text[:300] if error_text else None,
            },
        )

    discovered: list[str] = []
    filtered_out_competitors: list[dict[str, object]] = []
    relevance: list[dict[str, object]] = []
    extract_error: str | None = None
    extract_outcome: str | None = None
    snippet_count = len(all_snippets)
    if all_snippets:
        combined_results = "\n---\n".join(all_snippets[:DISCOVERY_SNIPPETS_TO_EXTRACT])
        extract_prompt = build_discovery_extract_user_prompt(
            search_results=combined_results,
            domain_context=domain_context,
            user_query=user_query,
        )
        fallback_prompt = build_discovery_extract_fallback_user_prompt(
            domain_context=domain_context,
            user_query=user_query,
        )
        try:
            harness_result = await complete_structured(
                model_slot="research",
                system_prompt=DISCOVERY_EXTRACT_SYSTEM_PROMPT,
                user_prompt=extract_prompt,
                output_model=DiscoveryExtractOutput,
                parser=DiscoveryExtractOutput.parse_llm_content,
                fallback_system_prompt=DISCOVERY_EXTRACT_SYSTEM_PROMPT,
                fallback_user_prompt=fallback_prompt,
                repair_user_prompt_builder=lambda errors: build_discovery_extract_repair_user_prompt(
                    validation_errors=errors,
                    domain_context=domain_context,
                ),
                log_event="discovery.harness.finish",
            )
            extract_outcome = harness_result.outcome
            if harness_result.value is not None:
                discovered, filtered_out_competitors, relevance = _filter_discovery_candidates(
                    candidates=harness_result.value.candidates,
                    snippets=all_snippets,
                )
            elif harness_result.llm_response.error is not None:
                extract_error = harness_result.llm_response.error[:300]
        except (KeyError, ValueError) as exc:
            extract_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            with bind_step(step_id):
                log.exception(
                    "discovery.extract_failed",
                    error_type=type(exc).__name__,
                    snippet_count=snippet_count,
                )

    with bind_step(step_id):
        log.info(
            "discovery.complete",
            discovered_count=len(discovered),
            discovered_competitors=discovered,
            snippet_count=snippet_count,
            snippet_samples=snippet_samples,
            filtered_out_competitors=filtered_out_competitors,
            relevance=relevance,
            queries=search_queries,
            extract_outcome=extract_outcome,
            extract_error=extract_error,
        )

    async with session_factory() as session:
        step_record = await session.get(Step, step_id)
        if step_record is not None:
            step_record.status = "completed" if discovered else "failed"
            step_record.finished_at = datetime.now(timezone.utc)
            step_record.payload = {
                **(step_record.payload or {}),
                "discovered_competitors": discovered,
                "snippet_count": snippet_count,
                "snippet_samples": snippet_samples,
                "filtered_out_competitors": filtered_out_competitors,
                "relevance": relevance,
                "extract_outcome": extract_outcome,
                "extract_error": extract_error,
            }
            await session.commit()

    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={"agent_name": "discovery", "discovered_competitors": discovered},
    )

    reconciled_plan_tree: dict[str, object] | None = None
    plan = coerce_plan_tree(state.get("plan_tree"))
    if discovered and plan is not None:
        intake_draft = state.get("intake_draft")
        focus_dimensions: list[str] | None = None
        if intake_draft is not None and hasattr(intake_draft, "focus_dimensions"):
            focus_dimensions = list(intake_draft.focus_dimensions)
        reconciled = reconcile_plan_tree_after_discovery(
            plan_tree=plan,
            discovered_competitors=discovered,
            focus_dimensions=focus_dimensions,
        )
        reconciled_plan_tree = reconciled.model_dump()
        async with session_factory() as session:
            run_row = await session.get(Run, run_id)
            if run_row is not None:
                run_row.plan_tree = reconciled_plan_tree
                await session.commit()
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.PLAN_RECONCILED,
            payload={
                "plan_id": reconciled.plan_id,
                "task_count": len(reconciled.tasks),
                "version": reconciled.version,
                "plan_tree": reconciled_plan_tree,
                "discovered_competitors": discovered,
            },
        )

    result: dict[str, object] = {
        "competitors": discovered,
        "discovered_competitors": discovered,
        "last_completed_node": None,
    }
    if reconciled_plan_tree is not None:
        result["plan_tree"] = reconciled_plan_tree
    return result
