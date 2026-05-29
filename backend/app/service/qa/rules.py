from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models.evidence import EvidenceRecord
from schemas.contracts import validate_section_id

RuleSeverity = Literal["blocking", "warning"]
RuleRejectTarget = Literal["supervisor", "researcher", "analyst", "writer"]


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


def rule_report_template_id_present(content_json: dict[str, object]) -> RuleResult:
    template_id_raw = content_json.get("template_id")
    passed = isinstance(template_id_raw, str) and bool(template_id_raw.strip())
    return RuleResult(
        rule_id="rule_report_template_id_present",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="template_id must be a non-empty string.",
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


def rule_writer_sections_must_have_content(content_json: dict[str, object]) -> RuleResult:
    sections_raw = content_json.get("sections")
    passed = False
    if isinstance(sections_raw, list) and sections_raw:
        passed = True
        for section in sections_raw:
            if not isinstance(section, dict):
                passed = False
                break
            section_id_raw = section.get("section_id")
            if not isinstance(section_id_raw, str):
                passed = False
                break
            try:
                validate_section_id(section_id_raw)
            except ValueError:
                passed = False
                break
            content_markdown_raw = section.get("content_markdown")
            if (
                not isinstance(content_markdown_raw, str)
                or len(content_markdown_raw.strip()) < 60
            ):
                passed = False
                break
    return RuleResult(
        rule_id="rule_writer_sections_must_have_content",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="Every section must include substantial content_markdown.",
    )


def rule_writer_must_cite_evidence(
    *,
    content_json: dict[str, object],
    allowed_evidence_ids: set[str],
) -> RuleResult:
    sections_raw = content_json.get("sections")
    referenced_evidence_ids: list[str] = []
    invalid_ref_detected = False
    if isinstance(sections_raw, list):
        for section in sections_raw:
            if not isinstance(section, dict):
                invalid_ref_detected = True
                continue
            evidence_refs_raw = section.get("evidence_refs")
            if not isinstance(evidence_refs_raw, list):
                continue
            for evidence_id in evidence_refs_raw:
                if not isinstance(evidence_id, str):
                    invalid_ref_detected = True
                    continue
                if evidence_id not in allowed_evidence_ids:
                    invalid_ref_detected = True
                    continue
                referenced_evidence_ids.append(evidence_id)
    passed = bool(referenced_evidence_ids) and not invalid_ref_detected
    return RuleResult(
        rule_id="rule_writer_must_cite_evidence",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="Writer sections must cite valid collected evidence_ids.",
    )


def rule_report_section_count_in_bounds(content_json: dict[str, object]) -> RuleResult:
    sections_raw = content_json.get("sections")
    section_count = len(sections_raw) if isinstance(sections_raw, list) else 0
    passed = 1 <= section_count <= 12
    return RuleResult(
        rule_id="rule_report_section_count_in_bounds",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="Report section count must be between 1 and 12.",
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
    allowed_evidence_ids: set[str],
) -> list[RuleResult]:
    return [
        rule_report_must_have_markdown_content(content_markdown),
        rule_report_template_id_present(content_json),
        rule_report_must_have_at_least_one_section(content_json),
        rule_report_section_count_in_bounds(content_json),
        rule_writer_sections_must_have_content(content_json),
        rule_writer_must_cite_evidence(
            content_json=content_json,
            allowed_evidence_ids=allowed_evidence_ids,
        ),
        rule_evidence_must_be_desensitized(evidence_items),
    ]
