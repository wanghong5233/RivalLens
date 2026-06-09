from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from core.tiers import resolve_tier_profile
from db.engine import get_session_factory
from models.report import Report
from models.step import Step
from schemas.ids import make_id
from schemas.qa import Approval, Rejection
from service.event_bus import RunEventType, emit_run_event
from service.llm.records import build_llm_call_record
from service.qa.engine import evaluate_report
from utils.log_node import log_node
from utils.logger import get_logger

log = get_logger("agents.qa")


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
            "failed_rule_count": 0,
            "failed_rule_ids": [],
            "warning_rule_ids": review_result.warning_rule_ids,
        }
    failed_rule_ids = list(review_result.failed_rule_ids)
    return {
        "target_step_id": target_step_id,
        "report_id": report_id,
        "qa_outcome": "rejected",
        "qa_reject_to": review_result.reject_to,
        "failed_rule_ids": failed_rule_ids,
        "failed_rule_count": len(failed_rule_ids),
        "warning_rule_ids": review_result.warning_rule_ids,
        "reject_to": review_result.reject_to,
    }


def _to_qa_reasons(rejection: Rejection) -> list[str]:
    # Prefer actionable rewrite hints (curated Chinese instruction, or the
    # rule's own message as fallback) so the writer's next attempt is targeted.
    hints = [hint for hint in rejection.remediation_hints.values() if hint]
    if hints:
        return hints
    reasons = [item for item in rejection.semantic_findings if item]
    if reasons:
        return reasons
    return list(rejection.failed_rule_ids)


def _report_has_writer_fallback_mode(content_json: dict[str, object]) -> bool:
    risk_callouts_raw = content_json.get("risk_callouts")
    if not isinstance(risk_callouts_raw, list):
        return False
    return "writer_fallback_mode" in risk_callouts_raw


def _state_report_depth(state: AgentState) -> str | None:
    intake_draft_raw = state.get("intake_draft")
    if isinstance(intake_draft_raw, dict):
        depth_raw = intake_draft_raw.get("report_depth")
        if isinstance(depth_raw, str):
            return depth_raw
    depth_raw = state.get("report_depth")
    if isinstance(depth_raw, str):
        return depth_raw
    return None


@log_node("qa")
async def qa_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for qa node.")

    session_factory = get_session_factory()
    pending_review_target_step_id = state.get("pending_review_target_step_id")
    qa_rejection_count = int(state.get("qa_rejection_count", 0))
    qa_reject_budget = resolve_tier_profile(_state_report_depth(state)).qa_reject_budget
    qa_step_id = make_id("step_")

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
    )
    promoted_qa_rule_ids_raw = semantic_metadata.get("promoted_qa_rule_ids", [])
    promoted_qa_rule_ids = (
        [item for item in promoted_qa_rule_ids_raw if isinstance(item, str)]
        if isinstance(promoted_qa_rule_ids_raw, list)
        else []
    )
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
    writer_fallback_mode = _report_has_writer_fallback_mode(report.content_json)
    approval_blocked_for_fallback = (
        isinstance(review_result, Approval) and writer_fallback_mode
    )
    if approval_blocked_for_fallback:
        updated_rejection_count = qa_rejection_count + 1
        is_force_degraded = updated_rejection_count > qa_reject_budget
    else:
        updated_rejection_count = (
            qa_rejection_count + 1 if isinstance(review_result, Rejection) else qa_rejection_count
        )
        is_force_degraded = (
            isinstance(review_result, Rejection)
            and updated_rejection_count > qa_reject_budget
        )
    qa_payload = _make_qa_payload(
        target_step_id=writer_step.step_id,
        report_id=report.report_id,
        review_result=review_result,
    )
    if approval_blocked_for_fallback:
        qa_payload["qa_outcome"] = "force_degraded" if is_force_degraded else "rejected"
        qa_payload["qa_reject_to"] = "supervisor" if is_force_degraded else "writer"
        qa_payload["reject_to"] = "supervisor" if is_force_degraded else "writer"
        qa_payload["failed_rule_ids"] = ["rule_writer_no_fallback_mode"]
        qa_payload["failed_rule_count"] = 1
    elif isinstance(review_result, Rejection) and is_force_degraded:
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
            session.add(build_llm_call_record(step_id=qa_step_id, response=semantic_llm_response))
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
    if isinstance(review_result, Approval) and not approval_blocked_for_fallback:
        event_qa_outcome = "approved"
        event_reject_to: str | None = None
    else:
        event_qa_outcome = "force_degraded" if is_force_degraded else "rejected"
        event_reject_to = (
            "supervisor"
            if is_force_degraded
            else (
                "writer"
                if approval_blocked_for_fallback
                else review_result.reject_to
            )
        )

    if isinstance(review_result, Approval) and not approval_blocked_for_fallback:
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
            writer_fallback_mode=writer_fallback_mode,
        )
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.QA_OUTCOME,
            step_id=qa_step_id,
            payload={
                "qa_outcome": event_qa_outcome,
                "reject_to": event_reject_to,
                "target_step_id": writer_step.step_id,
                "warning_rule_ids": qa_payload.get("warning_rule_ids", []),
            },
        )
        return {
            "last_completed_node": "writer",
            "pending_review_target_step_id": None,
            "qa_outcome": "approved",
            "qa_reject_to": None,
            "qa_rejection_count": qa_rejection_count,
            "qa_reasons": [],
            "qa_unsupported_numeric_claims": [],
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
    failed_rule_ids = (
        ["rule_writer_no_fallback_mode"]
        if approval_blocked_for_fallback
        else review_result.failed_rule_ids
    )
    log.info(
        "qa.outcome",
        outcome="force_degraded" if is_force_degraded else "rejected",
        reject_to=event_reject_to,
        failed_rule_ids=failed_rule_ids,
        retry_count=updated_rejection_count,
        target_step_id=writer_step.step_id,
        writer_fallback_mode=writer_fallback_mode,
    )
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.QA_OUTCOME,
        step_id=qa_step_id,
        payload={
            "qa_outcome": event_qa_outcome,
            "reject_to": event_reject_to,
            "target_step_id": writer_step.step_id,
            "failed_rule_count": len(failed_rule_ids),
            "warning_rule_ids": qa_payload.get("warning_rule_ids", []),
        },
    )
    qa_reasons = (
        ["Report must not be generated in deterministic writer fallback mode."]
        if approval_blocked_for_fallback
        else _to_qa_reasons(review_result)
    )
    unsupported_numeric_claims_raw = semantic_metadata.get("qa_unsupported_numeric_claims", [])
    unsupported_numeric_claims = (
        [item for item in unsupported_numeric_claims_raw if isinstance(item, dict)]
        if isinstance(unsupported_numeric_claims_raw, list)
        else []
    )
    return {
        "last_completed_node": "writer",
        "pending_review_target_step_id": None,
        "qa_outcome": "force_degraded" if is_force_degraded else "rejected",
        "qa_reject_to": event_reject_to,
        "qa_rejection_count": updated_rejection_count,
        "qa_reasons": qa_reasons,
        "qa_unsupported_numeric_claims": unsupported_numeric_claims,
        "status": "running",
    }
