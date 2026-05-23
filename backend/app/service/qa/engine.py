from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.evidence import EvidenceRecord
from models.report import Report
from schemas.ids import make_id
from schemas.qa import Approval, Rejection, RetryPolicy
from service.llm import (
    QA_SEMANTIC_ALLOWED_REJECT_TO,
    QA_SEMANTIC_SYSTEM_PROMPT,
    build_qa_semantic_fallback_user_prompt,
    build_qa_semantic_user_prompt,
)
from service.llm.client import get_llm_client
from service.llm.response import LLMResponse
from service.qa.rules import RuleResult, evaluate_fast_path_rules

MAX_QA_REJECTIONS = 3
SEMANTIC_RULE_ID = "rule_qa_semantic_audit"

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
    semantic_audit_passed: bool,
) -> Approval:
    return Approval(
        approval_id=f"approval_{uuid4().hex[:12]}",
        step_id=target_step_id,
        passed_rule_ids=[item.rule_id for item in rule_results if item.passed],
        semantic_audit_passed=semantic_audit_passed,
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
    semantic_audit_passed: bool = True,
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
        semantic_audit_passed=semantic_audit_passed,
    )


def _build_evidence_briefs(evidence_items: list[EvidenceRecord]) -> list[dict[str, str]]:
    briefs: list[dict[str, str]] = []
    for item in evidence_items:
        span = item.span if isinstance(item.span, dict) else {}
        dimension_raw = span.get("dimension")
        competitor_raw = span.get("competitor_id")
        briefs.append(
            {
                "evidence_id": item.id,
                "dimension": dimension_raw if isinstance(dimension_raw, str) else "unknown",
                "competitor_id": competitor_raw if isinstance(competitor_raw, str) else "unknown",
                "quote_preview": item.sanitized_text[:180],
                "source_url": item.source_url or "",
            }
        )
    return briefs


def _normalize_semantic_content(
    content: dict[str, object],
) -> dict[str, object] | None:
    audit_passed_raw = content.get("semantic_audit_passed")
    finding_raw = content.get("finding")
    reject_to_raw = content.get("reject_to")
    severity_raw = content.get("severity")
    required_fields_raw = content.get("required_fields")

    if not isinstance(audit_passed_raw, bool):
        return None
    if not isinstance(finding_raw, str) or not finding_raw.strip():
        return None
    if not isinstance(reject_to_raw, str) or reject_to_raw not in QA_SEMANTIC_ALLOWED_REJECT_TO:
        return None
    if not isinstance(severity_raw, str) or severity_raw not in {"blocking", "warning"}:
        return None
    if not isinstance(required_fields_raw, list):
        return None
    required_fields = [item for item in required_fields_raw if isinstance(item, str)]
    return {
        "semantic_audit_passed": audit_passed_raw,
        "finding": finding_raw.strip(),
        "reject_to": reject_to_raw,
        "severity": severity_raw,
        "required_fields": required_fields,
    }


def _semantic_rule_result(semantic_output: dict[str, object]) -> RuleResult:
    reject_to = semantic_output["reject_to"]
    if not isinstance(reject_to, str):
        raise RuntimeError("semantic reject_to is expected to be str after normalization.")

    severity = semantic_output["severity"]
    if not isinstance(severity, str):
        raise RuntimeError("semantic severity is expected to be str after normalization.")

    finding = semantic_output["finding"]
    if not isinstance(finding, str):
        raise RuntimeError("semantic finding is expected to be str after normalization.")

    semantic_audit_passed = semantic_output["semantic_audit_passed"]
    if not isinstance(semantic_audit_passed, bool):
        raise RuntimeError("semantic_audit_passed is expected to be bool after normalization.")

    return RuleResult(
        rule_id=SEMANTIC_RULE_ID,
        passed=semantic_audit_passed,
        severity=severity,  # validated above
        reject_to=reject_to,  # validated above
        message=finding,
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
) -> tuple[Approval | Rejection, LLMResponse | None, dict[str, object]]:
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
        ), None, {
            "qa_semantic_mode": "skipped_missing_report",
            "qa_semantic_audit_passed": False,
            "qa_semantic_error": "report_missing",
        }

    rule_results = evaluate_fast_path_rules(
        content_markdown=report.content_markdown,
        content_json=report.content_json,
        evidence_items=evidence_items,
        allowed_template_ids=allowed_template_ids,
    )
    evidence_briefs = _build_evidence_briefs(evidence_items)
    failed_rule_ids = [item.rule_id for item in rule_results if not item.passed]
    semantic_user_prompt = build_qa_semantic_user_prompt(
        report_markdown=report.content_markdown,
        report_json=report.content_json,
        failed_rule_ids=failed_rule_ids,
        evidence_briefs=evidence_briefs,
    )
    semantic_fallback_prompt = build_qa_semantic_fallback_user_prompt(
        failed_rule_ids=failed_rule_ids,
        evidence_count=len(evidence_items),
    )
    semantic_response = await get_llm_client().complete_json(
        model_slot="qa",
        system_prompt=QA_SEMANTIC_SYSTEM_PROMPT,
        user_prompt=semantic_user_prompt,
        fallback_system_prompt=QA_SEMANTIC_SYSTEM_PROMPT,
        fallback_user_prompt=semantic_fallback_prompt,
    )
    semantic_output = (
        _normalize_semantic_content(semantic_response.content)
        if semantic_response.error is None
        else None
    )
    semantic_mode: Literal["applied", "degraded_rule_only"] = "degraded_rule_only"
    semantic_audit_passed = False
    if semantic_output is not None:
        semantic_mode = "applied"
        semantic_rule = _semantic_rule_result(semantic_output)
        rule_results.append(semantic_rule)
        semantic_audit_passed = bool(semantic_output["semantic_audit_passed"])

    outcome = build_qa_outcome(
        target_step_id=target_step_id,
        reviewer_step_id=reviewer_step_id,
        rule_results=rule_results,
        qa_rejection_count=qa_rejection_count,
        semantic_audit_passed=semantic_audit_passed,
    )
    semantic_metadata = {
        "qa_semantic_mode": semantic_mode,
        "qa_semantic_audit_passed": semantic_audit_passed,
        "qa_semantic_error": semantic_response.error,
        "qa_semantic_fallback_used": semantic_response.fallback_used,
        "qa_semantic_fallback_reason": semantic_response.fallback_reason,
    }
    return outcome, semantic_response, semantic_metadata
