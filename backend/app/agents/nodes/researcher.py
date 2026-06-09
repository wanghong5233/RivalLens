from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit

from agents.state import AgentState
from agents.subgraphs.researcher import MAX_REACT_TURNS, ResearcherSubState, get_researcher_subgraph
from agents.tools.parse_page import (
    infer_source_type,
    official_hosts_for_competitor,
    source_matches_competitor,
)
from core.defaults import DEFAULT_FOCUS_DIMENSIONS
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.step import Step
from schemas.contracts import normalize_dimension_or_none, validate_dimension, validate_source_type
from schemas.ids import make_id
from schemas.supervisor import ConductResearch, FocusDimension
from service.collector.source_resolver import resolve_official_sources
from service.event_bus import RunEventType, emit_run_event
from service.desensitize import normalize_text_for_storage
from service.llm.records import build_llm_call_record_from_mapping
from service.collector.source_quality import is_low_semantic_text, source_blocklist_reason
from utils.log_node import log_node
from utils.logger import get_logger

log = get_logger("agents.researcher")

RESEARCHER_LOW_SEMANTIC_MIN_CHARS = 0


def _resolve_focus_dimensions(
    *,
    request: ConductResearch,
) -> list[FocusDimension]:
    focus_dimensions = list(request.focus_dimensions or [])
    if not focus_dimensions:
        focus_dimensions = list(DEFAULT_FOCUS_DIMENSIONS)
    if not focus_dimensions:
        raise RuntimeError(f"No focus_dimensions available for competitor_id={request.competitor_id}.")
    normalized: list[str] = []
    seen: set[str] = set()
    for dimension in focus_dimensions:
        normalized_dimension = validate_dimension(dimension)
        if normalized_dimension in seen:
            continue
        seen.add(normalized_dimension)
        normalized.append(normalized_dimension)
    return normalized


def _build_initial_substate(
    *,
    run_id: str,
    step_id: str,
    request: ConductResearch,
    focus_dimensions: list[FocusDimension],
    domain_hint: str | None,
    market_scope: str | None,
    response_language: str | None,
    reference_urls: list[str],
    resolved_official_urls: list[str],
    resolved_official_hosts: list[str],
    resolved_source_pages: list[dict[str, str]],
) -> ResearcherSubState:
    max_turns = max(request.max_iterations or MAX_REACT_TURNS, len(focus_dimensions))
    return {
        "run_id": run_id,
        "step_id": step_id,
        "research_topic": request.research_topic,
        "competitor_id": request.competitor_id,
        "focus_dimensions": list(focus_dimensions),
        "pending_dimensions": list(focus_dimensions),
        "queried_dimensions": [],
        "pending_action_args": {},
        "turn_count": 0,
        "max_turns": max_turns,
        "compression_count": 0,
        "last_compressed_turn": -1,
        "messages": [],
        "observations_log": [],
        "observation_briefs": [],
        "evidence_drafts": [],
        "llm_calls": [],
        "next_action": "tool_exec",
        "final_summary": "",
        "compressed_summary": "",
        "domain_hint": domain_hint,
        "market_scope": market_scope,
        "response_language": response_language,
        "reference_urls": reference_urls,
        "discovered_urls": [],
        "resolved_official_urls": resolved_official_urls,
        "resolved_official_hosts": resolved_official_hosts,
        "resolved_source_pages": resolved_source_pages,
        "search_call_count": 0,
        "official_fetch_count": 0,
        "coverage_matrix": {},
    }


def _candidate_source_urls_for_competitor(
    *,
    state: AgentState,
    competitor_id: str,
    reference_urls: list[str],
) -> list[str]:
    urls: list[str] = []
    discovered_sources_raw = state.get("discovered_competitor_sources")
    if isinstance(discovered_sources_raw, dict):
        payload = discovered_sources_raw.get(competitor_id)
        if isinstance(payload, dict):
            official_url_raw = payload.get("official_url")
            if isinstance(official_url_raw, str) and official_url_raw.strip():
                urls.append(official_url_raw.strip())
    plan_tree_raw = state.get("plan_tree")
    if isinstance(plan_tree_raw, dict):
        plan_sources_raw = plan_tree_raw.get("competitor_sources")
        if isinstance(plan_sources_raw, dict):
            plan_payload = plan_sources_raw.get(competitor_id)
            if isinstance(plan_payload, dict):
                plan_url_raw = plan_payload.get("official_url")
                if isinstance(plan_url_raw, str) and plan_url_raw.strip():
                    urls.append(plan_url_raw.strip())
    urls.extend(reference_urls)
    ordered: list[str] = []
    seen: set[str] = set()
    for item in urls:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _build_evidence_rows(
    *,
    run_id: str,
    step_id: str,
    collected_at: datetime,
    focus_dimensions: list[FocusDimension],
    evidence_drafts: list[dict[str, object]],
    observations_log: list[dict[str, object]],
    default_competitor_id: str,
    resolved_official_hosts: set[str] | None = None,
) -> tuple[list[EvidenceRecord], list[str], dict[str, object]]:
    dropped_reasons: dict[str, int] = {}

    def record_drop(reason: str | None) -> None:
        if reason is None:
            return
        dropped_reasons[reason] = dropped_reasons.get(reason, 0) + 1

    def dedupe_key(
        *,
        competitor_id: str,
        dimension: str | None,
        source_url: str | None,
        quote: str,
    ) -> tuple[str, str | None, str, str]:
        normalized_quote = normalize_text_for_storage(quote)
        quote_hash = hashlib.sha256(normalized_quote.encode("utf-8")).hexdigest()[:16]
        return (
            competitor_id,
            dimension,
            normalize_text_for_storage(source_url or ""),
            quote_hash,
        )

    normalized_runtime_official_hosts = {
        host.lower().removeprefix("www.").strip()
        for host in (resolved_official_hosts or set())
        if isinstance(host, str) and host.strip()
    }

    def official_hosts_for(competitor_id: str) -> set[str]:
        if competitor_id == default_competitor_id and normalized_runtime_official_hosts:
            return set(normalized_runtime_official_hosts)
        return official_hosts_for_competitor(competitor_id)

    def source_matches_hosts(
        *,
        source_url: str | None,
        hosts: set[str],
    ) -> bool | None:
        if not source_url or not hosts:
            return None
        host = urlsplit(source_url).netloc.lower().removeprefix("www.")
        if not host:
            return None
        normalized_hosts = {item.lower().removeprefix("www.") for item in hosts}
        if host in normalized_hosts:
            return True
        if any(host.endswith(f".{item}") for item in normalized_hosts):
            return True
        return False

    effective_drafts: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str | None, str, str]] = set()
    for draft in evidence_drafts:
        if not isinstance(draft, dict):
            continue
        competitor_id_raw = draft.get("competitor_id")
        quote_raw = draft.get("quote")
        if not isinstance(competitor_id_raw, str) or not isinstance(quote_raw, str):
            continue
        normalized_dimension, _ = normalize_dimension_or_none(
            draft.get("dimension"),
            allowed=focus_dimensions,
        )
        source_url_raw = draft.get("source_url")
        key = dedupe_key(
            competitor_id=competitor_id_raw,
            dimension=normalized_dimension,
            source_url=source_url_raw if isinstance(source_url_raw, str) else None,
            quote=quote_raw,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        effective_drafts.append(draft)

    for observation in observations_log:
        if not isinstance(observation, dict):
            continue
        result_raw = observation.get("result")
        if not isinstance(result_raw, dict):
            continue
        snippets_raw = result_raw.get("snippets")
        if not isinstance(snippets_raw, list):
            continue
        args_raw = observation.get("args")
        args = args_raw if isinstance(args_raw, dict) else {}
        fallback_dimension_raw = args.get("dimension")
        fallback_dimension = (
            fallback_dimension_raw
            if isinstance(fallback_dimension_raw, str) and fallback_dimension_raw.strip()
            else None
        )
        fallback_competitor_raw = args.get("competitor_id")
        fallback_competitor = (
            fallback_competitor_raw
            if isinstance(fallback_competitor_raw, str) and fallback_competitor_raw.strip()
            else default_competitor_id
        )
        for snippet_raw in snippets_raw:
            if not isinstance(snippet_raw, dict):
                continue
            quote_raw = snippet_raw.get("quote")
            if not isinstance(quote_raw, str) or not quote_raw.strip():
                continue
            metadata_raw = snippet_raw.get("metadata", {})
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
            dimension_raw = snippet_raw.get("dimension")
            if not isinstance(dimension_raw, str):
                dimension_candidate_raw = metadata.get("dimension")
                if isinstance(dimension_candidate_raw, str):
                    dimension_raw = dimension_candidate_raw
                else:
                    dimension_raw = fallback_dimension
            normalized_dimension, drop_reason = normalize_dimension_or_none(
                dimension_raw,
                allowed=focus_dimensions,
            )
            competitor_id_raw = snippet_raw.get("competitor_id")
            if not isinstance(competitor_id_raw, str):
                competitor_candidate_raw = metadata.get("competitor_id")
                if isinstance(competitor_candidate_raw, str):
                    competitor_id_raw = competitor_candidate_raw
                else:
                    competitor_id_raw = fallback_competitor
            source_url_raw = snippet_raw.get("source_url")
            source_url = source_url_raw if isinstance(source_url_raw, str) else None
            key = dedupe_key(
                competitor_id=competitor_id_raw,
                dimension=normalized_dimension,
                source_url=source_url,
                quote=quote_raw,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            effective_drafts.append(
                {
                    "dimension": normalized_dimension,
                    "competitor_id": competitor_id_raw,
                    "quote": quote_raw,
                    "sanitized_text": snippet_raw.get("sanitized_text", quote_raw),
                    "source_type": snippet_raw.get("source_type", "article"),
                    "source_url": snippet_raw.get("source_url"),
                    "source_title": snippet_raw.get("source_title"),
                    "desensitized": snippet_raw.get("desensitized", True),
                    "metadata": {
                        **metadata,
                        "dimension_drop_reason": drop_reason,
                    },
                }
            )

    evidence_rows: list[EvidenceRecord] = []
    evidence_ids: list[str] = []
    quality_floor_candidates: list[dict[str, object]] = []

    def append_evidence_row(candidate: dict[str, object]) -> None:
        evidence_id = make_id("ev_")
        evidence_ids.append(evidence_id)
        metadata_raw = candidate.get("metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        evidence_rows.append(
            EvidenceRecord(
                id=evidence_id,
                run_id=run_id,
                source_type=str(candidate["source_type"]),
                source_url=(
                    candidate["source_url"] if isinstance(candidate.get("source_url"), str) else None
                ),
                source_title=(
                    candidate["source_title"] if isinstance(candidate.get("source_title"), str) else None
                ),
                quote=str(candidate["quote"]),
                sanitized_text=str(candidate["sanitized_text"]),
                span={
                    **metadata,
                    "dimension": candidate.get("dimension"),
                    "competitor_id": candidate["competitor_id"],
                },
                collected_by=step_id,
                collected_at=collected_at,
                desensitized=bool(candidate.get("desensitized", False)),
            )
        )

    def source_quality_drop_reason(*, source_url: str | None, text: str) -> str | None:
        if source_blocklist_reason(source_url) is not None:
            return "source_blocklist"
        low_semantic, _ = is_low_semantic_text(
            text,
            min_chars=RESEARCHER_LOW_SEMANTIC_MIN_CHARS,
        )
        if low_semantic:
            return "low_semantic"
        return None

    for draft in effective_drafts:
        if not isinstance(draft, dict):
            continue
        dimension_raw = draft.get("dimension")
        competitor_id_raw = draft.get("competitor_id")
        quote_raw = draft.get("quote")
        sanitized_text_raw = draft.get("sanitized_text")
        source_type_raw = draft.get("source_type")
        source_url_raw = draft.get("source_url")
        source_title_raw = draft.get("source_title")
        metadata_raw = draft.get("metadata", {})
        if not isinstance(competitor_id_raw, str) or not isinstance(quote_raw, str):
            continue
        normalized_dimension, drop_reason = normalize_dimension_or_none(
            dimension_raw,
            allowed=focus_dimensions,
        )
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        upstream_drop_reason = metadata.get("dimension_drop_reason")
        if isinstance(upstream_drop_reason, str) and upstream_drop_reason:
            drop_reason = upstream_drop_reason
        record_drop(drop_reason)
        if isinstance(source_type_raw, str):
            try:
                normalized_source_type = validate_source_type(source_type_raw)
            except ValueError:
                normalized_source_type = "article"
        else:
            normalized_source_type = "article"
        sanitized_text = sanitized_text_raw if isinstance(sanitized_text_raw, str) else quote_raw
        source_url = source_url_raw if isinstance(source_url_raw, str) else None
        source_title = source_title_raw if isinstance(source_title_raw, str) else None
        quote_raw = normalize_text_for_storage(quote_raw)
        sanitized_text = normalize_text_for_storage(sanitized_text)
        if source_url is not None:
            source_url = normalize_text_for_storage(source_url)
        if source_title is not None:
            source_title = normalize_text_for_storage(source_title)
        competitor_official_hosts = official_hosts_for(competitor_id_raw)
        inferred_source_type = infer_source_type(
            source_url=source_url,
            official_hosts=competitor_official_hosts,
        )
        competitor_source_match = source_matches_hosts(
            source_url=source_url,
            hosts=competitor_official_hosts,
        )
        if competitor_source_match is None:
            competitor_source_match = source_matches_competitor(
                source_url=source_url,
                competitor_id=competitor_id_raw,
            )
        official_source_types = {"official_site", "docs", "pricing_page"}
        if normalized_source_type == "article" and inferred_source_type != "article":
            normalized_source_type = inferred_source_type
        elif (
            normalized_source_type in official_source_types
            and inferred_source_type not in official_source_types
        ):
            # Upstream tools classify against the union of all competitors' official
            # hosts, so a competitor's research result pointing at another vendor's
            # official domain can arrive mislabeled. Re-derive against this
            # competitor's own hosts and downgrade when it is not genuinely official.
            normalized_source_type = inferred_source_type
        metadata = {
            **metadata,
            "dimension_drop_reason": drop_reason,
            "competitor_source_match": competitor_source_match,
            "source_authority": (
                "official"
                if (
                    competitor_source_match is True
                    and normalized_source_type in {"official_site", "docs", "pricing_page"}
                )
                else "third_party"
            ),
        }
        candidate = {
            "dimension": normalized_dimension,
            "competitor_id": competitor_id_raw,
            "quote": quote_raw,
            "sanitized_text": sanitized_text,
            "source_type": normalized_source_type,
            "source_url": source_url,
            "source_title": source_title,
            "desensitized": bool(draft.get("desensitized", False)),
            "metadata": metadata,
        }
        quality_drop_reason = source_quality_drop_reason(
            source_url=source_url,
            text=sanitized_text or quote_raw,
        )
        if quality_drop_reason is not None:
            record_drop(quality_drop_reason)
            quality_floor_candidates.append(
                {
                    **candidate,
                    "metadata": {
                        **metadata,
                        "source_quality_drop_reason": quality_drop_reason,
                    },
                }
            )
            continue
        append_evidence_row(candidate)
    if not evidence_rows and quality_floor_candidates:
        floor_candidate = max(
            quality_floor_candidates,
            key=lambda item: len(str(item.get("sanitized_text") or item.get("quote") or "")),
        )
        floor_metadata_raw = floor_candidate.get("metadata")
        floor_metadata = floor_metadata_raw if isinstance(floor_metadata_raw, dict) else {}
        append_evidence_row(
            {
                **floor_candidate,
                "metadata": {
                    **floor_metadata,
                    "source_quality_floor": True,
                },
            }
        )
    return (
        evidence_rows,
        evidence_ids,
        {
            "count": sum(dropped_reasons.values()),
            "reasons": dropped_reasons,
        },
    )


def _build_llm_call_rows(
    *,
    step_id: str,
    llm_calls: list[dict[str, object]],
) -> list[LLMCall]:
    rows: list[LLMCall] = []
    for item in llm_calls:
        if not isinstance(item, dict):
            continue
        model_slot_raw = item.get("model_slot")
        if not isinstance(model_slot_raw, str):
            continue
        row = build_llm_call_record_from_mapping(step_id=step_id, item=item)
        if row is not None:
            rows.append(row)
    return rows


@log_node("researcher")
async def researcher_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for researcher node.")

    session_factory = get_session_factory()
    request = ConductResearch.model_validate(state.get("pending_tool_args", {}))
    domain_hint_raw = state.get("domain_hint")
    domain_hint = domain_hint_raw if isinstance(domain_hint_raw, str) and domain_hint_raw.strip() else None
    market_scope_raw = state.get("market_scope")
    market_scope = (
        market_scope_raw if isinstance(market_scope_raw, str) and market_scope_raw.strip() else None
    )
    response_language_raw = state.get("response_language")
    response_language = (
        response_language_raw
        if isinstance(response_language_raw, str) and response_language_raw in {"zh", "en"}
        else None
    )
    reference_urls_raw = state.get("reference_urls", [])
    reference_urls = (
        [item.strip() for item in reference_urls_raw if isinstance(item, str) and item.strip()]
        if isinstance(reference_urls_raw, list)
        else []
    )
    source_candidate_urls = _candidate_source_urls_for_competitor(
        state=state,
        competitor_id=request.competitor_id,
        reference_urls=reference_urls,
    )
    resolved_sources = await resolve_official_sources(
        competitor_id=request.competitor_id,
        competitor_name=request.competitor_id,
        candidate_urls=source_candidate_urls,
    )

    focus_dimensions = _resolve_focus_dimensions(request=request)
    step_id = make_id("step_")
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_START,
        step_id=step_id,
        payload={
            "agent_name": "researcher",
            "competitor_id": request.competitor_id,
        },
    )
    subgraph = get_researcher_subgraph()
    subgraph_input = _build_initial_substate(
        run_id=run_id,
        step_id=step_id,
        request=request,
        focus_dimensions=focus_dimensions,
        domain_hint=domain_hint,
        market_scope=market_scope,
        response_language=response_language,
        reference_urls=reference_urls,
        resolved_official_urls=list(resolved_sources.official_urls),
        resolved_official_hosts=list(resolved_sources.official_hosts),
        resolved_source_pages=[
            {
                "url": page.url,
                "source_type": page.source_type,
                "signal": page.signal,
            }
            for page in resolved_sources.key_pages
        ],
    )
    subgraph_output = await subgraph.ainvoke(subgraph_input)

    collected_at = datetime.now(timezone.utc)
    evidence_rows, evidence_ids, dropped_dimensions = _build_evidence_rows(
        run_id=run_id,
        step_id=step_id,
        collected_at=collected_at,
        focus_dimensions=focus_dimensions,
        evidence_drafts=list(subgraph_output.get("evidence_drafts", [])),
        observations_log=list(subgraph_output.get("observations_log", [])),
        default_competitor_id=request.competitor_id,
        resolved_official_hosts=set(resolved_sources.official_hosts),
    )
    llm_call_rows = _build_llm_call_rows(
        step_id=step_id,
        llm_calls=list(subgraph_output.get("llm_calls", [])),
    )
    coverage_matrix_raw = subgraph_output.get("coverage_matrix", {})
    coverage_matrix = coverage_matrix_raw if isinstance(coverage_matrix_raw, dict) else {}
    uncovered_dimensions = [
        dimension
        for dimension, row in coverage_matrix.items()
        if isinstance(dimension, str)
        and isinstance(row, dict)
        and not bool(row.get("covered"))
    ]
    step_payload = {
        **request.model_dump(),
        "domain_hint": domain_hint,
        "reference_urls": reference_urls,
        "focus_dimensions": focus_dimensions,
        "evidence_ids": evidence_ids,
        "react_turn_count": int(subgraph_output.get("turn_count", 0)),
        "compression_count": int(subgraph_output.get("compression_count", 0)),
        "queried_dimensions": list(subgraph_output.get("queried_dimensions", [])),
        "search_call_count": int(subgraph_output.get("search_call_count", 0)),
        "official_fetch_count": int(subgraph_output.get("official_fetch_count", 0)),
        "coverage_matrix": coverage_matrix,
        "coverage_summary": {
            "covered_dimension_count": len(coverage_matrix) - len(uncovered_dimensions),
            "total_dimension_count": len(coverage_matrix),
            "uncovered_dimensions": uncovered_dimensions,
        },
        "source_resolution": {
            "attempted_candidate_count": resolved_sources.attempted_candidate_count,
            "validated_candidate_count": resolved_sources.validated_candidate_count,
            "official_hosts": list(resolved_sources.official_hosts),
            "official_urls": list(resolved_sources.official_urls),
            "resolved_key_pages": [
                {
                    "url": page.url,
                    "source_type": page.source_type,
                    "signal": page.signal,
                }
                for page in resolved_sources.key_pages
            ],
        },
        "final_summary": str(subgraph_output.get("final_summary", "")),
        "dropped_dimensions": dropped_dimensions,
    }
    zero_evidence = len(evidence_rows) == 0
    if zero_evidence:
        step_payload = {
            **step_payload,
            "uncovered": True,
            "degraded_reason": "researcher_zero_evidence",
        }
    log.info(
        "researcher.dimension_drops",
        run_id=run_id,
        step_id=step_id,
        dropped_dimensions=dropped_dimensions,
    )

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="researcher",
            status="running",
            retry_count=0,
            payload=step_payload,
        )
        session.add(step)
        await session.flush()
        for evidence_row in evidence_rows:
            session.add(evidence_row)
        for llm_call_row in llm_call_rows:
            session.add(llm_call_row)
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="research_fragment",
                uri=f"memory://research/{run_id}/{request.competitor_id}",
                sha256=None,
                size_bytes=None,
            )
        )
        step.status = "degraded" if zero_evidence else "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
    for evidence_row in evidence_rows:
        span = evidence_row.span if isinstance(evidence_row.span, dict) else {}
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.EVIDENCE_COLLECTED,
            step_id=step_id,
            payload={
                "evidence_id": evidence_row.id,
                "competitor_id": span.get("competitor_id"),
                "dimension": span.get("dimension"),
                "source_type": evidence_row.source_type,
                "source_title": evidence_row.source_title,
                "source_url": evidence_row.source_url,
                "desensitized": bool(evidence_row.desensitized),
            },
        )
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={
            "agent_name": "researcher",
            "status": "degraded" if zero_evidence else "completed",
            "evidence_count": len(evidence_ids),
            "competitor_id": request.competitor_id,
            "degraded_reason": "researcher_zero_evidence" if zero_evidence else None,
        },
    )

    researched_competitors = list(state.get("researched_competitors", []))
    researched_competitor_delta = (
        [] if request.competitor_id in researched_competitors else [request.competitor_id]
    )

    result: AgentState = {
        "researched_competitors": researched_competitor_delta,
        "pending_tool_args": {},
        "last_completed_node": "researcher",
        "status": "running",
    }
    if zero_evidence:
        result["researcher_degraded_competitors"] = researched_competitor_delta or [request.competitor_id]
    return result
