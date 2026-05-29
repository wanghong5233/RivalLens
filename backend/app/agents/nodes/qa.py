from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from db.engine import get_session_factory
from models.llm_call import LLMCall
from models.report import Report
from models.step import Step
from schemas.ids import make_id
from schemas.qa import Approval, Rejection
from service.event_bus import RunEventType, emit_run_event
from service.industry_pack.registry import (
    IndustryPackNotFound,
    get_industry_pack_registry,
)
from service.qa.engine import MAX_QA_REJECTIONS, evaluate_report
from utils.log_node import log_node
from utils.logger import get_logger

log = get_logger("agents.qa")


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


async def _load_review_targets(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    pending_review_target_step_id: str | None,
) -> tuple[Step, Report]:
    async with session_factory() as session:
        if pending_review_target_step_id is not None:
            writer_step = await session.get(Step, pending_review_target_step_id)
            if (
                writer_step is not None
                and writer_step.run_id == run_id
                and writer_step.agent_name == "writer"
            ):
                pass
            else:
                writer_step = None
        else:
            writer_step = None

        if writer_step is None:
            writer_step = (
                await session.execute(
                    select(Step)
                    .where(Step.run_id == run_id, Step.agent_name == "writer")
                    .order_by(Step.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()
        if writer_step is None:
            raise RuntimeError(f"No writer step found for run_id={run_id} before QA review.")

        report = (
            await session.execute(
                select(Report)
                .where(Report.run_id == run_id)
                .order_by(Report.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if report is None:
            raise RuntimeError(f"No report found for run_id={run_id} before QA review.")

        return writer_step, report


def _make_qa_payload(
    *,
    target_step_id: str,
    report_id: str,
    review_result: Approval | Rejection,
) -> dict[str, object]:
    if isinstance(review_result, Approval):
        return {
            "target_step_id": target_step_id,
            "report_id": report_id,
            "qa_outcome": "approved",
            "qa_reject_to": None,
            "passed_rule_ids": review_result.passed_rule_ids,
        }
    return {
        "target_step_id": target_step_id,
        "report_id": report_id,
        "qa_outcome": "rejected",
        "qa_reject_to": review_result.reject_to,
        "failed_rule_ids": review_result.failed_rule_ids,
        "reject_to": review_result.reject_to,
    }


def _to_qa_reasons(rejection: Rejection) -> list[str]:
    reasons = [item for item in rejection.semantic_findings if item]
    if reasons:
        return reasons
    return list(rejection.failed_rule_ids)


@log_node("qa")
async def qa_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for qa node.")

    session_factory = _require_session_factory(state)
    pending_review_target_step_id = state.get("pending_review_target_step_id")
    qa_rejection_count = int(state.get("qa_rejection_count", 0))
    qa_step_id = make_id("step_")
    industry_pack = state.get("industry_pack")
    promoted_qa_rules = []
    if isinstance(industry_pack, str) and industry_pack:
        try:
            promoted_qa_rules = get_industry_pack_registry().get(
                industry_pack
            ).promoted_qa_rules
        except IndustryPackNotFound:
            promoted_qa_rules = []

    writer_step, report = await _load_review_targets(
        session_factory=session_factory,
        run_id=run_id,
        pending_review_target_step_id=pending_review_target_step_id,
    )
    review_result, semantic_llm_response, semantic_metadata = await evaluate_report(
        run_id=run_id,
        report_id=report.report_id,
        target_step_id=writer_step.step_id,
        reviewer_step_id=qa_step_id,
        session_factory=session_factory,
        qa_rejection_count=qa_rejection_count,
        promoted_qa_rules=promoted_qa_rules,
    )
    promoted_qa_rule_ids = [
        item.rule_id
        for item in promoted_qa_rules
    ]
    enforced_count_raw = semantic_metadata.get("promoted_qa_enforced_count", 0)
    parse_error_count_raw = semantic_metadata.get("promoted_qa_parse_error_count", 0)
    blocked_rule_ids_raw = semantic_metadata.get("promoted_qa_blocked_rule_ids", [])
    enforced_count = enforced_count_raw if isinstance(enforced_count_raw, int) else 0
    parse_error_count = parse_error_count_raw if isinstance(parse_error_count_raw, int) else 0
    blocked_rule_ids = (
        [item for item in blocked_rule_ids_raw if isinstance(item, str)]
        if isinstance(blocked_rule_ids_raw, list)
        else []
    )
    updated_rejection_count = (
        qa_rejection_count + 1 if isinstance(review_result, Rejection) else qa_rejection_count
    )
    is_force_degraded = (
        isinstance(review_result, Rejection)
        and updated_rejection_count > MAX_QA_REJECTIONS
    )
    qa_payload = _make_qa_payload(
        target_step_id=writer_step.step_id,
        report_id=report.report_id,
        review_result=review_result,
    )
    if isinstance(review_result, Rejection) and is_force_degraded:
        qa_payload["qa_outcome"] = "force_degraded"
        qa_payload["qa_reject_to"] = "supervisor"
        qa_payload["reject_to"] = "supervisor"

    async with session_factory() as session:
        step = Step(
            step_id=qa_step_id,
            run_id=run_id,
            agent_name="qa",
            status="running",
            retry_count=0,
            payload=qa_payload
            | semantic_metadata
            | {"promoted_qa_rule_ids": promoted_qa_rule_ids},
            rejection_reason=(
                review_result.model_dump()
                if isinstance(review_result, Rejection)
                else None
            ),
        )
        session.add(step)
        await session.flush()
        if semantic_llm_response is not None:
            semantic_error = (
                semantic_llm_response.error[:2000]
                if semantic_llm_response.error is not None
                else None
            )
            session.add(
                LLMCall(
                    step_id=qa_step_id,
                    model_slot=semantic_llm_response.model_slot,
                    provider=semantic_llm_response.provider,
                    model_name=semantic_llm_response.model_name,
                    prompt_hash=semantic_llm_response.prompt_hash,
                    prompt_tokens=semantic_llm_response.prompt_tokens,
                    completion_tokens=semantic_llm_response.completion_tokens,
                    latency_ms=semantic_llm_response.latency_ms,
                    error=semantic_error,
                )
            )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
    if isinstance(review_result, Approval):
        event_qa_outcome = "approved"
        event_reject_to: str | None = None
    else:
        event_qa_outcome = "force_degraded" if is_force_degraded else "rejected"
        event_reject_to = "supervisor" if is_force_degraded else review_result.reject_to

    if isinstance(review_result, Approval):
        log.info(
            "qa.promoted_rules",
            count=len(promoted_qa_rule_ids),
            rule_id_list=promoted_qa_rule_ids,
            enforced_count=enforced_count,
            parse_error_count=parse_error_count,
            blocked_rule_ids=blocked_rule_ids,
        )
        log.info(
            "qa.outcome",
            outcome="approved",
            retry_count=qa_rejection_count,
            target_step_id=writer_step.step_id,
        )
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.QA_OUTCOME,
            step_id=qa_step_id,
            payload={
                "qa_outcome": event_qa_outcome,
                "reject_to": event_reject_to,
                "target_step_id": writer_step.step_id,
            },
        )
        return {
            "last_completed_node": "writer",
            "pending_review_target_step_id": None,
            "qa_outcome": "approved",
            "qa_reject_to": None,
            "qa_rejection_count": qa_rejection_count,
            "qa_reasons": [],
            "status": "running",
        }

    log.info(
        "qa.promoted_rules",
        count=len(promoted_qa_rule_ids),
        rule_id_list=promoted_qa_rule_ids,
        enforced_count=enforced_count,
        parse_error_count=parse_error_count,
        blocked_rule_ids=blocked_rule_ids,
    )
    log.info(
        "qa.outcome",
        outcome="force_degraded" if is_force_degraded else "rejected",
        reject_to="supervisor" if is_force_degraded else review_result.reject_to,
        failed_rule_ids=review_result.failed_rule_ids,
        retry_count=updated_rejection_count,
        target_step_id=writer_step.step_id,
    )
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.QA_OUTCOME,
        step_id=qa_step_id,
        payload={
            "qa_outcome": event_qa_outcome,
            "reject_to": event_reject_to,
            "target_step_id": writer_step.step_id,
            "failed_rule_count": len(review_result.failed_rule_ids),
        },
    )
    return {
        "last_completed_node": "writer",
        "pending_review_target_step_id": None,
        "qa_outcome": "force_degraded" if is_force_degraded else "rejected",
        "qa_reject_to": "supervisor" if is_force_degraded else review_result.reject_to,
        "qa_rejection_count": updated_rejection_count,
        "qa_reasons": _to_qa_reasons(review_result),
        "status": "running",
    }
