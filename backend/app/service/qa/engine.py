from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.evidence import EvidenceRecord
from models.report import Report
from models.run import Run
from models.step import Step
from schemas.agent_outputs import QASemanticOutput
from schemas.ids import make_id
from schemas.qa import Approval, Rejection, RetryPolicy
from service.llm import (
    QA_SEMANTIC_SYSTEM_PROMPT,
    build_qa_semantic_fallback_user_prompt,
    build_qa_semantic_repair_user_prompt,
    build_qa_semantic_user_prompt,
)
from service.llm.harness import complete_structured
from service.llm.response import LLMResponse
from service.qa.numeric_claims import extract_numeric_claim_candidates
from service.qa.promoted_rules import evaluate_promoted_rule_yaml
from service.qa.rules import RuleResult, evaluate_fast_path_rules
from service.skill_store import get_skill_store
from utils.logger import get_logger

MAX_QA_REJECTIONS = 3
SEMANTIC_RULE_ID = "rule_qa_semantic_audit"
log = get_logger("service.qa.engine")


def _report_has_writer_fallback_mode(content_json: dict[str, object]) -> bool:
    risk_callouts_raw = content_json.get("risk_callouts")
    if not isinstance(risk_callouts_raw, list):
        return False
    return "writer_fallback_mode" in risk_callouts_raw

_RULE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "rule_report_must_have_markdown_content": ["reports.content_markdown"],
    "rule_report_template_id_present": ["reports.content_json.template_id"],
    "rule_report_must_have_at_least_one_section": ["reports.content_json.sections"],
    "rule_report_section_count_in_bounds": ["reports.content_json.sections"],
    "rule_writer_sections_must_have_content": ["reports.content_json.sections[].content_markdown"],
    "rule_writer_must_cite_evidence": ["reports.content_json.sections[].evidence_refs"],
    "rule_writer_no_fallback_mode": ["reports.content_json.risk_callouts"],
    "rule_evidence_must_be_desensitized": ["evidence.desensitized"],
    "rule_deep_report_min_char_count": ["reports.content_markdown"],
    "rule_deep_report_covers_target_sections": ["reports.content_json.sections[].section_id"],
    "rule_deep_sections_min_chars": ["reports.content_json.sections[].content_markdown"],
    "rule_deep_sections_cite_evidence": ["reports.content_json.sections[].evidence_refs"],
    "rule_report_exists": ["reports.report_id"],
}
_PROMOTED_RULE_REQUIRED_FIELDS = [
    "reports.content_json.sections[].evidence_refs",
    "reports.content_json.sections[].content_markdown",
]
_RULE_YAML_BLOCK_PATTERN = re.compile(r"```yaml\s*(?P<rule_yaml>.*?)```", re.DOTALL | re.IGNORECASE)
_RULE_ID_PATTERN = re.compile(r"^\s*id:\s*(?P<rule_id>[a-z0-9_:-]+)\s*$", re.IGNORECASE)


@dataclass(slots=True)
class PromotedQARulePayload:
    rule_id: str
    rule_yaml: str


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
        if item.rule_id.startswith("rule_promoted_"):
            required_fields.update(_PROMOTED_RULE_REQUIRED_FIELDS)

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


def _report_depth_from_run(run: Run | None) -> Literal["quick", "deep"]:
    if run is None or not isinstance(run.intake_draft, dict):
        return "quick"
    depth_raw = run.intake_draft.get("report_depth")
    return "deep" if depth_raw == "deep" else "quick"


def _extend_sections_from_values(*, sections: list[str], values: object) -> None:
    if not isinstance(values, list):
        return
    for item in values:
        if isinstance(item, str) and item and item not in sections:
            sections.append(item)


def _extend_sections_from_plan_tree(*, sections: list[str], plan_tree: dict[str, object] | None) -> None:
    if not isinstance(plan_tree, dict):
        return
    tasks_raw = plan_tree.get("tasks")
    if not isinstance(tasks_raw, list):
        return
    for task_raw in tasks_raw:
        if not isinstance(task_raw, dict):
            continue
        _extend_sections_from_values(sections=sections, values=task_raw.get("focus_dimensions"))


def _target_sections_for_report(*, run: Run | None, writer_step: Step | None) -> list[str]:
    sections: list[str] = []
    if writer_step is not None and isinstance(writer_step.payload, dict):
        target_sections_raw = writer_step.payload.get("target_sections")
        if isinstance(target_sections_raw, list):
            _extend_sections_from_values(sections=sections, values=target_sections_raw)
            return sections
        _extend_sections_from_values(sections=sections, values=writer_step.payload.get("sections"))
    if run is not None:
        _extend_sections_from_plan_tree(sections=sections, plan_tree=run.plan_tree)
        if isinstance(run.intake_draft, dict):
            _extend_sections_from_values(
                sections=sections,
                values=run.intake_draft.get("focus_dimensions"),
            )
    return sections


def _extract_rule_yaml_from_skill_content(content: str) -> str | None:
    matched = _RULE_YAML_BLOCK_PATTERN.search(content)
    if matched is None:
        stripped = content.strip()
        return stripped if stripped else None
    rule_yaml = matched.group("rule_yaml").strip()
    return rule_yaml or None


def _extract_rule_id(rule_yaml: str, *, fallback_id: str) -> str:
    for line in rule_yaml.splitlines():
        matched = _RULE_ID_PATTERN.match(line)
        if matched is not None:
            return matched.group("rule_id")
    return fallback_id


def _load_promoted_qa_rules_from_skill_store() -> list[PromotedQARulePayload]:
    store = get_skill_store()
    promoted_rules: list[PromotedQARulePayload] = []
    for skill_name in store.list_by_applies_to("qa_rule"):
        parsed = store.load(skill_name)
        if parsed is None:
            continue
        rule_yaml = _extract_rule_yaml_from_skill_content(parsed.content)
        if rule_yaml is None:
            continue
        promoted_rules.append(
            PromotedQARulePayload(
                rule_id=_extract_rule_id(rule_yaml, fallback_id=skill_name),
                rule_yaml=rule_yaml,
            )
        )
    return promoted_rules


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


def _unsupported_numeric_claims(semantic_output: dict[str, object]) -> list[dict[str, object]]:
    items_raw = semantic_output.get("unsupported_numeric_claims")
    if not isinstance(items_raw, list):
        return []
    return [item for item in items_raw if isinstance(item, dict)]


def _apply_numeric_claim_gate(
    *,
    semantic_output: dict[str, object],
    qa_rejection_count: int,
    has_blocking_failures_pre_semantic: bool,
) -> dict[str, object]:
    unsupported_claims = _unsupported_numeric_claims(semantic_output)
    if not unsupported_claims:
        return semantic_output
    if qa_rejection_count >= 1 and not has_blocking_failures_pre_semantic:
        return {
            **semantic_output,
            "semantic_audit_passed": True,
            "severity": "warning",
            "reject_to": "writer",
            "finding": (
                "Unsupported numeric claims remained after retry; accepted with warning "
                "metadata so the report can surface unverifiable numbers."
            ),
        }
    required_fields_raw = semantic_output.get("required_fields")
    existing_required_fields = (
        [item for item in required_fields_raw if isinstance(item, str)]
        if isinstance(required_fields_raw, list)
        else []
    )
    return {
        **semantic_output,
        "semantic_audit_passed": False,
        "severity": "blocking",
        "reject_to": "writer",
        "finding": (
            "Report contains numeric claims that are not supported by cited evidence; "
            "rewrite with supported numbers or downgrade them to qualitative statements."
        ),
        "required_fields": sorted(
            {
                *existing_required_fields,
                "reports.content_json.sections[].content_markdown",
                "reports.content_json.sections[].evidence_refs",
            }
        ),
    }


def _build_promoted_rule_results(
    *,
    promoted_qa_rules: list[PromotedQARulePayload],
    content_json: dict[str, object],
    evidence_items: list[EvidenceRecord],
    now: datetime | None = None,
) -> tuple[list[RuleResult], dict[str, object]]:
    observed_rules: list[RuleResult] = []
    if not promoted_qa_rules:
        return observed_rules, {
            "promoted_qa_enforced_count": 0,
            "promoted_qa_parse_error_count": 0,
            "promoted_qa_blocked_rule_ids": [],
        }
    current_time = now or datetime.now(timezone.utc)
    evidence_by_id = {item.id: item for item in evidence_items}
    parse_error_count = 0
    enforced_count = 0
    for item in promoted_qa_rules:
        evaluated = evaluate_promoted_rule_yaml(
            promoted_rule_id=f"rule_promoted_{item.rule_id}",
            rule_yaml=item.rule_yaml,
            content_json=content_json,
            evidence_by_id=evidence_by_id,
            now=current_time,
        )
        observed_rules.append(
            evaluated.result
        )
        if evaluated.enforced:
            enforced_count += 1
        if evaluated.parse_error is not None:
            parse_error_count += 1
    blocked_rule_ids = [
        item.rule_id
        for item in observed_rules
        if (not item.passed and item.severity == "blocking")
    ]
    return observed_rules, {
        "promoted_qa_enforced_count": enforced_count,
        "promoted_qa_parse_error_count": parse_error_count,
        "promoted_qa_blocked_rule_ids": blocked_rule_ids,
    }


def _build_qa_fast_path_log_fields(
    *,
    mode: str,
    rule_results: list[RuleResult],
    promoted_qa_rule_ids: list[str],
    promoted_rule_metadata: dict[str, object],
) -> dict[str, object]:
    failed_rule_ids = [item.rule_id for item in rule_results if not item.passed]
    blocking_failed_rule_ids = [
        item.rule_id
        for item in rule_results
        if (not item.passed and item.severity == "blocking")
    ]
    return {
        "mode": mode,
        "rule_count": len(rule_results),
        "failed_rule_count": len(failed_rule_ids),
        "blocking_failed_rule_count": len(blocking_failed_rule_ids),
        "failed_rule_ids": failed_rule_ids,
        "blocking_failed_rule_ids": blocking_failed_rule_ids,
        "promoted_qa_rule_ids": promoted_qa_rule_ids,
        "promoted_qa_blocked_rule_ids": list(
            promoted_rule_metadata.get("promoted_qa_blocked_rule_ids", [])
        ),
        "promoted_qa_enforced_count": promoted_rule_metadata.get(
            "promoted_qa_enforced_count",
            0,
        ),
        "promoted_qa_parse_error_count": promoted_rule_metadata.get(
            "promoted_qa_parse_error_count",
            0,
        ),
    }


def _build_qa_slow_path_log_fields(
    *,
    mode: str,
    rule_results: list[RuleResult],
    semantic_output: dict[str, object] | None,
    semantic_response: LLMResponse,
    schema_error: str | None,
) -> dict[str, object]:
    failed_rule_ids = [item.rule_id for item in rule_results if not item.passed]
    finding_raw = semantic_output.get("finding") if semantic_output is not None else None
    reject_to_raw = semantic_output.get("reject_to") if semantic_output is not None else None
    severity_raw = semantic_output.get("severity") if semantic_output is not None else None
    unsupported_numeric_claims = (
        _unsupported_numeric_claims(semantic_output) if semantic_output is not None else []
    )
    semantic_audit_passed = (
        bool(semantic_output.get("semantic_audit_passed"))
        if semantic_output is not None
        else False
    )
    return {
        "mode": mode,
        "semantic_audit_passed": semantic_audit_passed,
        "fallback_used": semantic_response.fallback_used,
        "has_error": semantic_response.error is not None,
        "failed_rule_count": len(failed_rule_ids),
        "failed_rule_ids": failed_rule_ids,
        "semantic_finding_preview": (
            finding_raw[:300] if isinstance(finding_raw, str) else None
        ),
        "semantic_reject_to": reject_to_raw if isinstance(reject_to_raw, str) else None,
        "semantic_severity": severity_raw if isinstance(severity_raw, str) else None,
        "unsupported_numeric_claim_count": len(unsupported_numeric_claims),
        "schema_error": schema_error,
    }


async def evaluate_report(
    *,
    run_id: str,
    report_id: str,
    target_step_id: str,
    reviewer_step_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    qa_rejection_count: int,
    promoted_qa_rules: list[PromotedQARulePayload] | None = None,
) -> tuple[Approval | Rejection, LLMResponse | None, dict[str, object]]:
    promoted_rules = promoted_qa_rules or _load_promoted_qa_rules_from_skill_store()
    promoted_rule_ids = [item.rule_id for item in promoted_rules]
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        report = await session.get(Report, report_id)
        writer_step = await session.get(Step, target_step_id)
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
        log.info(
            "qa.fast_path",
            **_build_qa_fast_path_log_fields(
                mode="skipped_missing_report",
                rule_results=[missing_report],
                promoted_qa_rule_ids=promoted_rule_ids,
                promoted_rule_metadata={
                    "promoted_qa_enforced_count": 0,
                    "promoted_qa_parse_error_count": 0,
                    "promoted_qa_blocked_rule_ids": [],
                },
            ),
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
            "promoted_qa_rule_ids": promoted_rule_ids,
        }

    report_depth = _report_depth_from_run(run)
    target_sections = _target_sections_for_report(run=run, writer_step=writer_step)
    rule_results = evaluate_fast_path_rules(
        content_markdown=report.content_markdown,
        content_json=report.content_json,
        evidence_items=evidence_items,
        allowed_evidence_ids={item.id for item in evidence_items},
        report_depth=report_depth,
        target_sections=target_sections,
    )
    promoted_rule_results, promoted_rule_metadata = _build_promoted_rule_results(
        promoted_qa_rules=promoted_rules,
        content_json=report.content_json,
        evidence_items=evidence_items,
    )
    rule_results.extend(promoted_rule_results)
    has_blocking_failures_pre_semantic = any(
        (not item.passed and item.severity == "blocking") for item in rule_results
    )
    failed_rule_ids = [item.rule_id for item in rule_results if not item.passed]
    log.info(
        "qa.fast_path",
        **_build_qa_fast_path_log_fields(
            mode="applied",
            rule_results=rule_results,
            promoted_qa_rule_ids=promoted_rule_ids,
            promoted_rule_metadata=promoted_rule_metadata,
        ),
    )
    evidence_briefs = _build_evidence_briefs(evidence_items)
    numeric_claim_candidates = extract_numeric_claim_candidates(
        report_json=report.content_json,
        evidence_items=evidence_items,
    )
    numeric_claims_for_prompt = [item.to_prompt_dict() for item in numeric_claim_candidates]
    semantic_user_prompt = build_qa_semantic_user_prompt(
        report_markdown=report.content_markdown,
        report_json=report.content_json,
        failed_rule_ids=failed_rule_ids,
        evidence_briefs=evidence_briefs,
        report_depth=report_depth,
        target_sections=target_sections,
        numeric_claims=numeric_claims_for_prompt,
    )
    semantic_fallback_prompt = build_qa_semantic_fallback_user_prompt(
        failed_rule_ids=failed_rule_ids,
        evidence_count=len(evidence_items),
    )
    harness_result = await complete_structured(
        model_slot="qa",
        system_prompt=QA_SEMANTIC_SYSTEM_PROMPT,
        user_prompt=semantic_user_prompt,
        output_model=QASemanticOutput,
        parser=QASemanticOutput.parse_llm_content,
        fallback_system_prompt=QA_SEMANTIC_SYSTEM_PROMPT,
        fallback_user_prompt=semantic_fallback_prompt,
        repair_user_prompt_builder=lambda errors: build_qa_semantic_repair_user_prompt(
            validation_errors=errors,
            failed_rule_ids=failed_rule_ids,
        ),
        log_event="qa.harness.finish",
    )
    semantic_response = harness_result.llm_response
    semantic_output = (
        harness_result.value.to_normalized_dict()
        if harness_result.value is not None
        else None
    )
    semantic_mode: Literal["applied", "degraded_rule_only"] = "degraded_rule_only"
    semantic_audit_passed = False
    if semantic_output is not None:
        semantic_mode = "applied"
        semantic_output = _apply_numeric_claim_gate(
            semantic_output=semantic_output,
            qa_rejection_count=qa_rejection_count,
            has_blocking_failures_pre_semantic=has_blocking_failures_pre_semantic,
        )
        semantic_reject_to_raw = semantic_output.get("reject_to")
        semantic_audit_passed_raw = semantic_output.get("semantic_audit_passed")
        if (
            semantic_audit_passed_raw is False
            and semantic_reject_to_raw in {"researcher", "analyst"}
            and len(evidence_items) >= 3
        ):
            # When evidence is already sufficient, route rewrite to writer first to avoid costly
            # re-research loops that rarely improve report grounding quality.
            semantic_output = {
                **semantic_output,
                "reject_to": "writer",
            }
        if (
            semantic_audit_passed_raw is False
            and semantic_reject_to_raw in {"researcher", "analyst", "writer"}
            and qa_rejection_count >= 1
            and len(evidence_items) >= 12
            and not has_blocking_failures_pre_semantic
            and not _report_has_writer_fallback_mode(report.content_json)
        ):
            # If deterministic QA already passed and semantic retry still bounces between
            # analyst/researcher, stop the loop and accept with warning-level metadata.
            semantic_output = {
                **semantic_output,
                "semantic_audit_passed": True,
                "severity": "warning",
                "reject_to": "writer",
                "finding": (
                    "Semantic audit remained unstable after retry; accepted because "
                    "deterministic QA passed and evidence coverage is sufficient."
                ),
            }
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
        "qa_numeric_claim_count": len(numeric_claims_for_prompt),
        "qa_unsupported_numeric_claims": (
            _unsupported_numeric_claims(semantic_output) if semantic_output is not None else []
        ),
        "promoted_qa_rule_ids": promoted_rule_ids,
        **promoted_rule_metadata,
    }
    log.info(
        "qa.slow_path",
        **_build_qa_slow_path_log_fields(
            mode=semantic_mode,
            rule_results=rule_results,
            semantic_output=semantic_output,
            semantic_response=semantic_response,
            schema_error=harness_result.schema_error,
        ),
    )
    return outcome, semantic_response, semantic_metadata
