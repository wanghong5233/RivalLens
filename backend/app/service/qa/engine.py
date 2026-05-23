from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.evidence import EvidenceRecord
from models.report import Report
from schemas.ids import make_id
from schemas.qa import Approval, Rejection, RetryPolicy
from service.qa.rules import RuleResult, evaluate_fast_path_rules

MAX_QA_REJECTIONS = 3

_RULE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "rule_report_must_have_markdown_content": ["reports.content_markdown"],
    "rule_report_template_id_valid": ["reports.content_json.template_id"],
    "rule_report_must_have_at_least_one_section": ["reports.content_json.sections"],
    "rule_evidence_must_be_desensitized": ["evidence.desensitized"],
    "rule_report_exists": ["reports.report_id"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_approval(
    *,
    target_step_id: str,
    reviewer_step_id: str,
    rule_results: list[RuleResult],
) -> Approval:
    return Approval(
        approval_id=f"approval_{uuid4().hex[:12]}",
        step_id=target_step_id,
        passed_rule_ids=[item.rule_id for item in rule_results if item.passed],
        semantic_audit_passed=True,
        reviewer_step_id=reviewer_step_id,
        created_at=_now_iso(),
    )


def _build_rejection(
    *,
    target_step_id: str,
    reviewer_step_id: str,
    qa_rejection_count: int,
    failed_rules: list[RuleResult],
) -> Rejection:
    primary_rule = failed_rules[0]
    required_fields: set[str] = set()
    for item in failed_rules:
        required_fields.update(_RULE_REQUIRED_FIELDS.get(item.rule_id, []))

    return Rejection(
        rejection_id=make_id("rejection_"),
        step_id=target_step_id,
        reject_to=primary_rule.reject_to,
        failed_rule_ids=[item.rule_id for item in failed_rules],
        semantic_findings=[item.message for item in failed_rules],
        required_fields=sorted(required_fields),
        retry_policy=RetryPolicy(
            max_retry=MAX_QA_REJECTIONS,
            current_retry=qa_rejection_count + 1,
            fallback_action="finalize_degraded",
        ),
        severity="blocking",
        reviewer_step_id=reviewer_step_id,
        created_at=_now_iso(),
    )


def build_qa_outcome(
    *,
    target_step_id: str,
    reviewer_step_id: str,
    rule_results: list[RuleResult],
    qa_rejection_count: int,
) -> Approval | Rejection:
    failed_blocking_rules = [
        item for item in rule_results if (not item.passed and item.severity == "blocking")
    ]
    if failed_blocking_rules:
        return _build_rejection(
            target_step_id=target_step_id,
            reviewer_step_id=reviewer_step_id,
            qa_rejection_count=qa_rejection_count,
            failed_rules=failed_blocking_rules,
        )
    return _build_approval(
        target_step_id=target_step_id,
        reviewer_step_id=reviewer_step_id,
        rule_results=rule_results,
    )


async def evaluate_report(
    *,
    run_id: str,
    report_id: str,
    target_step_id: str,
    reviewer_step_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    qa_rejection_count: int,
    allowed_template_ids: set[str] | None = None,
) -> Approval | Rejection:
    async with session_factory() as session:
        report = await session.get(Report, report_id)
        evidence_items = (
            await session.execute(
                select(EvidenceRecord).where(EvidenceRecord.run_id == run_id)
            )
        ).scalars().all()

    if report is None or report.run_id != run_id:
        missing_report = RuleResult(
            rule_id="rule_report_exists",
            passed=False,
            severity="blocking",
            reject_to="writer",
            message=f"QA cannot find report_id={report_id} in run_id={run_id}.",
        )
        return build_qa_outcome(
            target_step_id=target_step_id,
            reviewer_step_id=reviewer_step_id,
            rule_results=[missing_report],
            qa_rejection_count=qa_rejection_count,
        )

    rule_results = evaluate_fast_path_rules(
        content_markdown=report.content_markdown,
        content_json=report.content_json,
        evidence_items=evidence_items,
        allowed_template_ids=allowed_template_ids,
    )
    return build_qa_outcome(
        target_step_id=target_step_id,
        reviewer_step_id=reviewer_step_id,
        rule_results=rule_results,
        qa_rejection_count=qa_rejection_count,
    )
