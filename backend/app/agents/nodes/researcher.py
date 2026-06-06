from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from agents.state import AgentState
from agents.subgraphs.researcher import MAX_REACT_TURNS, ResearcherSubState, get_researcher_subgraph
from core.defaults import DEFAULT_FOCUS_DIMENSIONS
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.step import Step
from schemas.contracts import normalize_dimension_or_none, validate_dimension, validate_source_type
from schemas.ids import make_id
from schemas.supervisor import ConductResearch, FocusDimension
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
    reference_urls: list[str],
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
        "reference_urls": reference_urls,
        "discovered_urls": [],
    }


def _build_evidence_rows(
    *,
    run_id: str,
    step_id: str,
    collected_at: datetime,
    focus_dimensions: list[FocusDimension],
    evidence_drafts: list[dict[str, object]],
    observations_log: list[dict[str, object]],
    default_competitor_id: str,
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
        metadata = {
            **metadata,
            "dimension_drop_reason": drop_reason,
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
    reference_urls_raw = state.get("reference_urls", [])
    reference_urls = (
        [item.strip() for item in reference_urls_raw if isinstance(item, str) and item.strip()]
        if isinstance(reference_urls_raw, list)
        else []
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
        reference_urls=reference_urls,
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
    )
    llm_call_rows = _build_llm_call_rows(
        step_id=step_id,
        llm_calls=list(subgraph_output.get("llm_calls", [])),
    )
    step_payload = {
        **request.model_dump(),
        "domain_hint": domain_hint,
        "reference_urls": reference_urls,
        "focus_dimensions": focus_dimensions,
        "evidence_ids": evidence_ids,
        "react_turn_count": int(subgraph_output.get("turn_count", 0)),
        "compression_count": int(subgraph_output.get("compression_count", 0)),
        "queried_dimensions": list(subgraph_output.get("queried_dimensions", [])),
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
