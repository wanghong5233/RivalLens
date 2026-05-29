from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from agents.subgraphs.researcher import MAX_REACT_TURNS, ResearcherSubState, get_researcher_subgraph
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.step import Step
from schemas.contracts import validate_dimension, validate_source_type
from schemas.ids import make_id
from schemas.supervisor import ConductResearch, FocusDimension
from service.event_bus import RunEventType, emit_run_event
from utils.log_node import log_node


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _resolve_focus_dimensions(
    *,
    request: ConductResearch,
) -> list[FocusDimension]:
    focus_dimensions = list(request.focus_dimensions or [])
    if not focus_dimensions:
        focus_dimensions = ["feature", "pricing", "user_feedback"]
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
    request: ConductResearch,
    focus_dimensions: list[FocusDimension],
    domain_hint: str | None,
    reference_urls: list[str],
) -> ResearcherSubState:
    return {
        "run_id": run_id,
        "research_topic": request.research_topic,
        "competitor_id": request.competitor_id,
        "focus_dimensions": list(focus_dimensions),
        "pending_dimensions": list(focus_dimensions),
        "queried_dimensions": [],
        "pending_action_args": {},
        "turn_count": 0,
        "max_turns": request.max_iterations or MAX_REACT_TURNS,
        "compression_count": 0,
        "last_compressed_turn": -1,
        "messages": [],
        "observations_log": [],
        "evidence_drafts": [],
        "llm_calls": [],
        "next_action": "tool_exec",
        "final_summary": "",
        "domain_hint": domain_hint,
        "reference_urls": reference_urls,
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
) -> tuple[list[EvidenceRecord], list[str]]:
    allowed_dimensions = set(focus_dimensions)
    effective_drafts = list(evidence_drafts)
    if True:
        seen_keys: set[tuple[str, str, str, str]] = set()
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
                else "feature"
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
                try:
                    normalized_dimension = validate_dimension(dimension_raw)
                except ValueError:
                    normalized_dimension = "feature"
                if normalized_dimension not in allowed_dimensions:
                    if focus_dimensions:
                        normalized_dimension = focus_dimensions[0]
                    else:
                        continue
                competitor_id_raw = snippet_raw.get("competitor_id")
                if not isinstance(competitor_id_raw, str):
                    competitor_candidate_raw = metadata.get("competitor_id")
                    if isinstance(competitor_candidate_raw, str):
                        competitor_id_raw = competitor_candidate_raw
                    else:
                        competitor_id_raw = fallback_competitor
                source_url_raw = snippet_raw.get("source_url")
                source_url = source_url_raw if isinstance(source_url_raw, str) else ""
                dedupe_key = (
                    competitor_id_raw,
                    normalized_dimension,
                    quote_raw[:80],
                    source_url,
                )
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
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
                        "metadata": metadata,
                    }
                )

    evidence_rows: list[EvidenceRecord] = []
    evidence_ids: list[str] = []
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
        if not isinstance(dimension_raw, str) or not isinstance(competitor_id_raw, str) or not isinstance(quote_raw, str):
            continue
        normalized_dimension = validate_dimension(dimension_raw)
        if normalized_dimension not in allowed_dimensions:
            if focus_dimensions:
                normalized_dimension = focus_dimensions[0]
            else:
                continue
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
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        evidence_id = make_id("ev_")
        evidence_ids.append(evidence_id)
        evidence_rows.append(
            EvidenceRecord(
                id=evidence_id,
                run_id=run_id,
                source_type=normalized_source_type,
                source_url=source_url,
                source_title=source_title,
                quote=quote_raw,
                sanitized_text=sanitized_text,
                span={
                    **metadata,
                    "dimension": normalized_dimension,
                    "competitor_id": competitor_id_raw,
                },
                collected_by=step_id,
                collected_at=collected_at,
                desensitized=bool(draft.get("desensitized", False)),
            )
        )
    if not evidence_rows:
        raise RuntimeError("Researcher subgraph finalized without any evidence drafts.")
    return evidence_rows, evidence_ids


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
        provider_raw = item.get("provider")
        model_name_raw = item.get("model_name")
        prompt_hash_raw = item.get("prompt_hash")
        prompt_tokens_raw = item.get("prompt_tokens")
        completion_tokens_raw = item.get("completion_tokens")
        latency_ms_raw = item.get("latency_ms")
        error_raw = item.get("error")
        rows.append(
            LLMCall(
                step_id=step_id,
                model_slot=model_slot_raw,
                provider=provider_raw if isinstance(provider_raw, str) else None,
                model_name=model_name_raw if isinstance(model_name_raw, str) else None,
                prompt_hash=prompt_hash_raw if isinstance(prompt_hash_raw, str) else None,
                prompt_tokens=prompt_tokens_raw if isinstance(prompt_tokens_raw, int) else None,
                completion_tokens=completion_tokens_raw
                if isinstance(completion_tokens_raw, int)
                else None,
                latency_ms=latency_ms_raw if isinstance(latency_ms_raw, int) else None,
                error=error_raw if isinstance(error_raw, str) else None,
            )
        )
    return rows


@log_node("researcher")
async def researcher_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for researcher node.")

    session_factory = _require_session_factory(state)
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
    subgraph = get_researcher_subgraph()
    subgraph_input = _build_initial_substate(
        run_id=run_id,
        request=request,
        focus_dimensions=focus_dimensions,
        domain_hint=domain_hint,
        reference_urls=reference_urls,
    )
    subgraph_output = await subgraph.ainvoke(subgraph_input)

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
    collected_at = datetime.now(timezone.utc)
    evidence_rows, evidence_ids = _build_evidence_rows(
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
    }

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
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={
            "agent_name": "researcher",
            "status": "completed",
            "evidence_count": len(evidence_ids),
            "competitor_id": request.competitor_id,
        },
    )

    researched_competitors = list(state.get("researched_competitors", []))
    researched_competitor_delta = (
        [] if request.competitor_id in researched_competitors else [request.competitor_id]
    )

    return {
        "researched_competitors": researched_competitor_delta,
        "pending_tool_args": {},
        "last_completed_node": "researcher",
        "status": "running",
    }
