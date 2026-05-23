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
from schemas.ids import make_id
from schemas.supervisor import ConductResearch, FocusDimension
from service.industry_pack.models import IndustryPack
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _require_industry_pack_id(state: AgentState) -> str:
    industry_pack_id = state.get("industry_pack")
    if industry_pack_id is None:
        raise RuntimeError("AgentState.industry_pack is required for researcher node.")
    return industry_pack_id


def _resolve_pack(industry_pack_id: str) -> IndustryPack:
    pack_registry = get_industry_pack_registry()
    try:
        return pack_registry.get(industry_pack_id)
    except IndustryPackNotFound as exc:
        raise RuntimeError(f"industry_pack={industry_pack_id} is not loaded.") from exc


def _resolve_focus_dimensions(
    *,
    request: ConductResearch,
    pack: IndustryPack,
) -> list[FocusDimension]:
    focus_dimensions = list(request.focus_dimensions or pack.default_focus_dimensions)
    if not focus_dimensions:
        raise RuntimeError(
            f"No focus_dimensions available for industry_pack={pack.id} and competitor_id={request.competitor_id}."
        )
    for dimension in focus_dimensions:
        if dimension not in {"feature", "pricing", "user_feedback", "positioning", "tech_stack"}:
            raise RuntimeError(f"Unsupported focus dimension: {dimension}.")
    return focus_dimensions


def _build_initial_substate(
    *,
    run_id: str,
    pack_id: str,
    request: ConductResearch,
    focus_dimensions: list[FocusDimension],
) -> ResearcherSubState:
    return {
        "run_id": run_id,
        "industry_pack_id": pack_id,
        "research_topic": request.research_topic,
        "competitor_id": request.competitor_id,
        "focus_dimensions": list(focus_dimensions),
        "pending_dimensions": list(focus_dimensions),
        "queried_dimensions": [],
        "pending_action_args": {},
        "turn_count": 0,
        "max_turns": request.max_iterations or MAX_REACT_TURNS,
        "compression_count": 0,
        "messages": [],
        "observations_log": [],
        "evidence_drafts": [],
        "llm_calls": [],
        "next_action": "tool_exec",
        "final_summary": "",
    }


def _build_evidence_rows(
    *,
    run_id: str,
    step_id: str,
    collected_at: datetime,
    pack_id: str,
    focus_dimensions: list[FocusDimension],
    evidence_drafts: list[dict[str, object]],
) -> tuple[list[EvidenceRecord], list[str]]:
    evidence_rows: list[EvidenceRecord] = []
    evidence_ids: list[str] = []
    allowed_dimensions = set(focus_dimensions)
    for draft in evidence_drafts:
        if not isinstance(draft, dict):
            continue
        dimension_raw = draft.get("dimension")
        competitor_id_raw = draft.get("competitor_id")
        quote_raw = draft.get("quote")
        source_url_raw = draft.get("source_url")
        source_title_raw = draft.get("source_title")
        if (
            not isinstance(dimension_raw, str)
            or dimension_raw not in allowed_dimensions
            or not isinstance(competitor_id_raw, str)
            or not isinstance(quote_raw, str)
            or not isinstance(source_url_raw, str)
            or not isinstance(source_title_raw, str)
        ):
            continue
        evidence_id = make_id("ev_")
        evidence_ids.append(evidence_id)
        evidence_rows.append(
            EvidenceRecord(
                id=evidence_id,
                run_id=run_id,
                source_type="industry_pack_snapshot",
                source_url=source_url_raw,
                source_title=source_title_raw,
                quote=quote_raw,
                sanitized_text=quote_raw,
                span={
                    "dimension": dimension_raw,
                    "competitor_id": competitor_id_raw,
                    "pack_id": pack_id,
                },
                collected_by=step_id,
                collected_at=collected_at,
                desensitized=bool(draft.get("desensitized", True)),
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


async def researcher_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for researcher node.")

    industry_pack_id = _require_industry_pack_id(state)
    session_factory = _require_session_factory(state)
    request = ConductResearch.model_validate(state.get("pending_tool_args", {}))
    pack = _resolve_pack(industry_pack_id)
    competitor = pack.competitors.get(request.competitor_id)
    if competitor is None:
        raise RuntimeError(
            f"competitor_id={request.competitor_id} not found in industry_pack={pack.id}."
        )

    focus_dimensions = _resolve_focus_dimensions(request=request, pack=pack)
    subgraph = get_researcher_subgraph()
    subgraph_input = _build_initial_substate(
        run_id=run_id,
        pack_id=pack.id,
        request=request,
        focus_dimensions=focus_dimensions,
    )
    subgraph_output = await subgraph.ainvoke(subgraph_input)

    step_id = make_id("step_")
    collected_at = datetime.now(timezone.utc)
    evidence_rows, evidence_ids = _build_evidence_rows(
        run_id=run_id,
        step_id=step_id,
        collected_at=collected_at,
        pack_id=pack.id,
        focus_dimensions=focus_dimensions,
        evidence_drafts=list(subgraph_output.get("evidence_drafts", [])),
    )
    llm_call_rows = _build_llm_call_rows(
        step_id=step_id,
        llm_calls=list(subgraph_output.get("llm_calls", [])),
    )
    step_payload = {
        **request.model_dump(),
        "pack_id": pack.id,
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

    researched_competitors = list(state.get("researched_competitors", []))
    if request.competitor_id not in researched_competitors:
        researched_competitors.append(request.competitor_id)

    return {
        **state,
        "researched_competitors": researched_competitors,
        "pending_tool_args": {},
        "last_completed_node": "researcher",
        "status": "running",
    }
