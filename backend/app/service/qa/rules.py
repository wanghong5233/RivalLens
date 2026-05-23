from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models.evidence import EvidenceRecord

RuleSeverity = Literal["blocking", "warning"]
RuleRejectTarget = Literal["supervisor", "researcher", "analyst", "writer"]

DEFAULT_ALLOWED_TEMPLATE_IDS = {"battlecard_default"}


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    passed: bool
    severity: RuleSeverity
    reject_to: RuleRejectTarget
    message: str


def rule_report_must_have_markdown_content(content_markdown: str) -> RuleResult:
    passed = bool(content_markdown.strip())
    return RuleResult(
        rule_id="rule_report_must_have_markdown_content",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="Report markdown must be non-empty.",
    )


def rule_report_template_id_valid(
    *,
    content_json: dict[str, object],
    allowed_template_ids: set[str] | None = None,
) -> RuleResult:
    allowed = allowed_template_ids or DEFAULT_ALLOWED_TEMPLATE_IDS
    template_id_raw = content_json.get("template_id")
    passed = isinstance(template_id_raw, str) and template_id_raw in allowed
    return RuleResult(
        rule_id="rule_report_template_id_valid",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message=f"template_id must be in {sorted(allowed)}.",
    )


def rule_report_must_have_at_least_one_section(content_json: dict[str, object]) -> RuleResult:
    sections_raw = content_json.get("sections")
    passed = isinstance(sections_raw, list) and len(sections_raw) >= 1
    return RuleResult(
        rule_id="rule_report_must_have_at_least_one_section",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="Report must contain at least one section.",
    )


def rule_evidence_must_be_desensitized(evidence_items: list[EvidenceRecord]) -> RuleResult:
    passed = all(item.desensitized for item in evidence_items)
    return RuleResult(
        rule_id="rule_evidence_must_be_desensitized",
        passed=passed,
        severity="blocking",
        reject_to="researcher",
        message="All evidence rows must be desensitized before downstream reporting.",
    )


def evaluate_fast_path_rules(
    *,
    content_markdown: str,
    content_json: dict[str, object],
    evidence_items: list[EvidenceRecord],
    allowed_template_ids: set[str] | None = None,
) -> list[RuleResult]:
    return [
        rule_report_must_have_markdown_content(content_markdown),
        rule_report_template_id_valid(
            content_json=content_json,
            allowed_template_ids=allowed_template_ids,
        ),
        rule_report_must_have_at_least_one_section(content_json),
        rule_evidence_must_be_desensitized(evidence_items),
    ]
