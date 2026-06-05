from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from db.engine import get_session_factory
from models.evidence import EvidenceRecord
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from schemas.ids import make_id
from service.event_bus import RunEventType, emit_run_event
from service.llm.records import build_llm_call_record
from service.skill_curator import generate_skill_candidates
from utils.logger import bind_run, get_logger

log = get_logger("service.skill_curator.tasks")


def _serialize_decisions(rows: list[SupervisorDecisionRecord]) -> list[dict[str, object]]:
    return [
        {
            "id": row.id,
            "iteration": row.iteration,
            "chosen_tool": row.chosen_tool,
            "tool_args": row.tool_args,
            "reasoning_summary": row.reasoning_summary,
            "triggered_by": row.triggered_by,
            "outcome": row.outcome,
            "outcome_recorded_at": row.outcome_recorded_at.isoformat()
            if row.outcome_recorded_at is not None
            else None,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


async def _load_curator_context(run_id: str) -> dict[str, Any]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run_status_row = (
            await session.execute(
                select(func.count())
                .select_from(Step)
                .where(
                    Step.run_id == run_id,
                    Step.agent_name == "qa",
                    Step.rejection_reason.is_not(None),
                )
            )
        ).scalar_one()
        qa_reasons_raw = (
            await session.execute(
                select(Step.rejection_reason)
                .where(
                    Step.run_id == run_id,
                    Step.agent_name == "qa",
                    Step.rejection_reason.is_not(None),
                )
                .order_by(Step.created_at.asc())
            )
        ).scalars().all()
        decision_rows = (
            await session.execute(
                select(SupervisorDecisionRecord)
                .where(SupervisorDecisionRecord.run_id == run_id)
                .order_by(SupervisorDecisionRecord.created_at.asc())
            )
        ).scalars().all()
        evidence_source_rows = (
            await session.execute(
                select(EvidenceRecord.source_type, func.count(EvidenceRecord.id))
                .where(EvidenceRecord.run_id == run_id)
                .group_by(EvidenceRecord.source_type)
            )
        ).all()
        run_row = (
            await session.execute(
                select(Step.run_id).where(Step.run_id == run_id).limit(1)
            )
        ).scalar_one_or_none()
    if run_row is None:
        raise RuntimeError(f"run_id={run_id} not found before skill curator task.")
    qa_reasons: list[str] = []
    for item in qa_reasons_raw:
        if not isinstance(item, dict):
            continue
        findings_raw = item.get("semantic_findings")
        if isinstance(findings_raw, list):
            qa_reasons.extend(entry for entry in findings_raw if isinstance(entry, str))
        failed_rule_ids_raw = item.get("failed_rule_ids")
        if isinstance(failed_rule_ids_raw, list):
            qa_reasons.extend(entry for entry in failed_rule_ids_raw if isinstance(entry, str))
    source_counts: dict[str, int] = {}
    total_evidence_count = 0
    for source_type, count in evidence_source_rows:
        if not isinstance(source_type, str):
            continue
        source_counts[source_type] = int(count)
        total_evidence_count += int(count)
    return {
        "qa_rejection_count": int(run_status_row),
        "qa_reasons": qa_reasons,
        "supervisor_decisions": _serialize_decisions(decision_rows),
        "evidence_source_counts": source_counts,
        "total_evidence_count": total_evidence_count,
    }


def _default_tags(domain_hint: str | None) -> list[str]:
    if domain_hint is None:
        return ["generic", "curator_error"]
    normalized = domain_hint.strip().lower().replace(" ", "_")
    if not normalized:
        return ["generic", "curator_error"]
    return [normalized[:48], "curator_error"]


def _to_error_candidate(*, run_id: str, tags: list[str], error: str) -> SkillCandidateRecord:
    return SkillCandidateRecord(
        id=make_id("skill_"),
        candidate_type="qa_rule",
        applies_to="qa_rule",
        tags=tags,
        payload={"error_type": "skill_curator_task_failed", "run_id": run_id},
        rationale="Skill curator async task failed to generate candidates.",
        supporting_run_ids=[run_id],
        confidence="low",
        status="staging",
        error=error[:2000],
    )


def _normalize_domain_hint(domain_hint: str | None) -> str | None:
    if domain_hint is None:
        return None
    normalized = domain_hint.strip()
    return normalized or None


async def run_skill_curator_for_run(*, run_id: str, domain_hint: str | None) -> None:
    normalized_domain_hint = _normalize_domain_hint(domain_hint)
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.CURATOR_START,
        payload={"domain_hint": normalized_domain_hint},
    )
    with bind_run(run_id):
        log.info("skill_curator.task.start", domain_hint=normalized_domain_hint)
        session_factory = get_session_factory()
        try:
            context = await _load_curator_context(run_id)
            generation_result = await generate_skill_candidates(
                run_id=run_id,
                domain_hint=normalized_domain_hint,
                qa_rejection_count=int(context["qa_rejection_count"]),
                qa_reasons=list(context["qa_reasons"]),
                supervisor_decisions=list(context["supervisor_decisions"]),
                evidence_source_counts=dict(context["evidence_source_counts"]),
                total_evidence_count=int(context["total_evidence_count"]),
            )

            async with session_factory() as session:
                llm_response = generation_result.llm_response
                llm_error = generation_result.error or llm_response.error
                llm_error_trimmed = llm_error[:2000] if llm_error is not None else None
                step_id = make_id("step_")
                step = Step(
                    step_id=step_id,
                    run_id=run_id,
                    agent_name="skill_curator",
                    status="running",
                    retry_count=0,
                    payload={
                        "candidate_count": len(generation_result.candidates),
                        "qa_rejection_count": int(context["qa_rejection_count"]),
                        "evidence_source_counts": dict(context["evidence_source_counts"]),
                        "llm_provider": llm_response.provider,
                        "llm_prompt_preview": llm_response.prompt_preview,
                        "llm_fallback_used": llm_response.fallback_used,
                        "llm_fallback_reason": llm_response.fallback_reason,
                    },
                )
                session.add(step)
                await session.flush()
                session.add(
                    build_llm_call_record(
                        step_id=step_id,
                        response=llm_response,
                        error=llm_error_trimmed,
                    )
                )
                if llm_error_trimmed is not None and not generation_result.candidates:
                    session.add(
                        _to_error_candidate(
                            run_id=run_id,
                            tags=_default_tags(normalized_domain_hint),
                            error=llm_error_trimmed,
                        )
                    )
                else:
                    for candidate in generation_result.candidates:
                        session.add(
                            SkillCandidateRecord(
                                id=make_id("skill_"),
                                candidate_type=candidate.candidate_type,
                                applies_to=candidate.candidate_type,
                                tags=candidate.tags or _default_tags(normalized_domain_hint),
                                payload=candidate.payload,
                                rationale=candidate.rationale,
                                supporting_run_ids=candidate.supporting_run_ids or [run_id],
                                confidence=candidate.confidence,
                                status="staging",
                                error=None,
                            )
                        )
                step.status = "completed"
                step.finished_at = datetime.now(timezone.utc)
                await session.commit()
        except (RuntimeError, SQLAlchemyError) as exc:
            log.info(
                "skill_curator.task.failed",
                error=str(exc)[:500],
            )
            async with session_factory() as session:
                session.add(
                    _to_error_candidate(
                        run_id=run_id,
                        tags=_default_tags(normalized_domain_hint),
                        error=str(exc),
                    )
                )
                await session.commit()
            await emit_run_event(
                run_id=run_id,
                event_type=RunEventType.CURATOR_FINISH,
                payload={"status": "failed", "error": str(exc)[:500]},
            )
            return
        log.info("skill_curator.task.finish", status="completed")
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.CURATOR_FINISH,
        payload={"status": "completed"},
    )
