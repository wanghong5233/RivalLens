from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from db.engine import get_session_factory
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from schemas.ids import make_id
from service.skill_curator import SkillCuratorCandidate, generate_skill_candidates


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _serialize_decisions(decisions_raw: object) -> list[dict[str, object]]:
    if not isinstance(decisions_raw, list):
        return []
    serialized: list[dict[str, object]] = []
    for item in decisions_raw:
        if isinstance(item, dict):
            serialized.append(item)
            continue
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                serialized.append(dumped)
    return serialized


async def _load_evidence_source_stats(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> tuple[dict[str, int], int]:
    async with session_factory() as session:
        grouped_rows = (
            await session.execute(
                select(EvidenceRecord.source_type, func.count(EvidenceRecord.id))
                .where(EvidenceRecord.run_id == run_id)
                .group_by(EvidenceRecord.source_type)
            )
        ).all()
    source_counts: dict[str, int] = {}
    total_count = 0
    for source_type, count in grouped_rows:
        if not isinstance(source_type, str):
            continue
        source_count = int(count)
        source_counts[source_type] = source_count
        total_count += source_count
    return source_counts, total_count


def _build_error_candidate(
    *,
    run_id: str,
    industry_pack: str,
    error_message: str,
) -> SkillCandidateRecord:
    trimmed_error = error_message[:2000]
    return SkillCandidateRecord(
        id=make_id("skill_"),
        candidate_type="qa_rule",
        industry_pack=industry_pack,
        payload={
            "error_type": "skill_curator_generation_failed",
            "run_id": run_id,
        },
        rationale="Skill curator failed to generate reusable candidates for this run.",
        supporting_run_ids=[run_id],
        confidence="low",
        status="staging",
        error=trimmed_error,
    )


def _to_record(
    *,
    candidate: SkillCuratorCandidate,
    run_id: str,
    industry_pack: str,
) -> SkillCandidateRecord:
    return SkillCandidateRecord(
        id=make_id("skill_"),
        candidate_type=candidate.candidate_type,
        industry_pack=industry_pack,
        payload=candidate.payload,
        rationale=candidate.rationale,
        supporting_run_ids=candidate.supporting_run_ids or [run_id],
        confidence=candidate.confidence,
        status="staging",
        error=None,
    )


async def skill_curator_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for skill_curator node.")
    industry_pack = state.get("industry_pack")
    if industry_pack is None:
        raise RuntimeError("AgentState.industry_pack is required for skill_curator node.")

    session_factory = _require_session_factory(state)
    step_id = make_id("step_")
    qa_reasons = [item for item in state.get("qa_reasons", []) if isinstance(item, str)]
    qa_rejection_count = int(state.get("qa_rejection_count", 0))
    decisions = _serialize_decisions(state.get("decisions"))
    source_counts, total_evidence_count = await _load_evidence_source_stats(
        session_factory=session_factory,
        run_id=run_id,
    )
    generation_result = await generate_skill_candidates(
        run_id=run_id,
        industry_pack=industry_pack,
        qa_rejection_count=qa_rejection_count,
        qa_reasons=qa_reasons,
        supervisor_decisions=decisions,
        evidence_source_counts=source_counts,
        total_evidence_count=total_evidence_count,
    )

    llm_response = generation_result.llm_response
    llm_call_error = generation_result.error or llm_response.error
    llm_call_error_trimmed = llm_call_error[:2000] if llm_call_error is not None else None
    candidates = generation_result.candidates
    persisted_candidate_count = len(candidates) if llm_call_error is None else 1

    try:
        async with session_factory() as session:
            step = Step(
                step_id=step_id,
                run_id=run_id,
                agent_name="skill_curator",
                status="running",
                retry_count=0,
                payload={
                    "candidate_count": persisted_candidate_count,
                    "qa_rejection_count": qa_rejection_count,
                    "evidence_source_counts": source_counts,
                    "llm_provider": llm_response.provider,
                    "llm_prompt_preview": llm_response.prompt_preview,
                    "llm_fallback_used": llm_response.fallback_used,
                    "llm_fallback_reason": llm_response.fallback_reason,
                },
            )
            session.add(step)
            await session.flush()
            session.add(
                LLMCall(
                    step_id=step_id,
                    model_slot=llm_response.model_slot,
                    provider=llm_response.provider,
                    model_name=llm_response.model_name,
                    prompt_hash=llm_response.prompt_hash,
                    prompt_tokens=llm_response.prompt_tokens,
                    completion_tokens=llm_response.completion_tokens,
                    latency_ms=llm_response.latency_ms,
                    error=llm_call_error_trimmed,
                )
            )
            if llm_call_error_trimmed is not None:
                session.add(
                    _build_error_candidate(
                        run_id=run_id,
                        industry_pack=industry_pack,
                        error_message=llm_call_error_trimmed,
                    )
                )
            else:
                for candidate in candidates:
                    session.add(
                        _to_record(
                            candidate=candidate,
                            run_id=run_id,
                            industry_pack=industry_pack,
                        )
                    )
            step.status = "completed"
            step.finished_at = datetime.now(timezone.utc)
            await session.commit()
    except SQLAlchemyError:
        return {
            "status": "completed",
            "qa_outcome": None,
            "qa_reject_to": None,
            "qa_reasons": [],
        }

    return {
        "status": "completed",
        "qa_outcome": None,
        "qa_reject_to": None,
        "qa_reasons": [],
    }
