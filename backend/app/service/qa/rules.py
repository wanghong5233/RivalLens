from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.defaults import (
    DEEP_REPORT_MIN_CHAR_COUNT,
    DEEP_REPORT_MIN_EVIDENCE_REFS_PER_SECTION,
    DEEP_REPORT_MIN_SECTION_CHAR_COUNT,
    DEEP_REPORT_MIN_SECTION_COVERAGE_RATE,
)
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


def rule_writer_no_fallback_mode(content_json: dict[str, object]) -> RuleResult:
    risk_callouts_raw = content_json.get("risk_callouts")
    has_fallback_flag = (
        isinstance(risk_callouts_raw, list)
        and "writer_fallback_mode" in risk_callouts_raw
    )
    passed = not has_fallback_flag
    return RuleResult(
        rule_id="rule_writer_no_fallback_mode",
        passed=passed,
        severity="blocking",
        reject_to="writer",
        message="Report must not be generated in deterministic writer fallback mode.",
    )


def _iter_report_sections(content_json: dict[str, object]) -> list[dict[str, object]]:
    sections_raw = content_json.get("sections")
    if not isinstance(sections_raw, list):
        return []
    return [item for item in sections_raw if isinstance(item, dict)]


def _section_id(section: dict[str, object]) -> str | None:
    value = section.get("section_id")
    return value if isinstance(value, str) and value else None


def _section_markdown(section: dict[str, object]) -> str:
    value = section.get("content_markdown")
    return value.strip() if isinstance(value, str) else ""


def _section_evidence_refs(section: dict[str, object]) -> list[str]:
    refs_raw = section.get("evidence_refs")
    if not isinstance(refs_raw, list):
        return []
    return [item for item in refs_raw if isinstance(item, str) and item]


def _executive_summary_is_present(content_json: dict[str, object]) -> bool:
    summary_raw = content_json.get("executive_summary")
    return isinstance(summary_raw, str) and bool(summary_raw.strip())


def _covered_report_section_ids(content_json: dict[str, object]) -> set[str]:
    section_ids = {
        section_id
        for section in _iter_report_sections(content_json)
        for section_id in [_section_id(section)]
        if section_id is not None
    }
    if _executive_summary_is_present(content_json):
        section_ids.add("executive_summary")
    return section_ids


def _normalized_target_sections(target_sections: list[str] | None) -> list[str]:
    if not target_sections:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in target_sections:
        if item in seen:
            continue
        try:
            validate_section_id(item)
        except ValueError:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def rule_deep_report_min_char_count(
    *,
    content_markdown: str,
    min_chars: int = DEEP_REPORT_MIN_CHAR_COUNT,
) -> RuleResult:
    char_count = len(content_markdown.strip())
    return RuleResult(
        rule_id="rule_deep_report_min_char_count",
        passed=char_count >= min_chars,
        severity="blocking",
        reject_to="writer",
        message=f"Deep report markdown must be at least {min_chars} chars (actual={char_count}).",
    )


def rule_deep_report_covers_target_sections(
    *,
    content_json: dict[str, object],
    target_sections: list[str] | None,
    min_coverage_rate: float = DEEP_REPORT_MIN_SECTION_COVERAGE_RATE,
) -> RuleResult:
    targets = _normalized_target_sections(target_sections)
    if not targets:
        return RuleResult(
            rule_id="rule_deep_report_covers_target_sections",
            passed=True,
            severity="blocking",
            reject_to="writer",
            message="Deep report section coverage skipped because no target sections were resolved.",
        )
    actual_sections = _covered_report_section_ids(content_json)
    covered_count = sum(1 for target in targets if target in actual_sections)
    coverage_rate = covered_count / len(targets)
    missing = [target for target in targets if target not in actual_sections]
    return RuleResult(
        rule_id="rule_deep_report_covers_target_sections",
        passed=coverage_rate >= min_coverage_rate,
        severity="blocking",
        reject_to="writer",
        message=(
            "Deep report must cover target sections "
            f"(coverage={coverage_rate:.2f}, min={min_coverage_rate:.2f}, missing={missing})."
        ),
    )


def rule_deep_sections_min_chars(
    *,
    content_json: dict[str, object],
    min_chars: int = DEEP_REPORT_MIN_SECTION_CHAR_COUNT,
) -> RuleResult:
    sections = _iter_report_sections(content_json)
    short_sections = [
        _section_id(section) or "unknown"
        for section in sections
        if len(_section_markdown(section)) < min_chars
    ]
    return RuleResult(
        rule_id="rule_deep_sections_min_chars",
        passed=bool(sections) and not short_sections,
        severity="blocking",
        reject_to="writer",
        message=(
            f"Every deep report section must be at least {min_chars} chars "
            f"(short_sections={short_sections})."
        ),
    )


def rule_deep_sections_cite_evidence(
    *,
    content_json: dict[str, object],
    min_refs_per_section: int = DEEP_REPORT_MIN_EVIDENCE_REFS_PER_SECTION,
) -> RuleResult:
    sections = _iter_report_sections(content_json)
    under_cited_sections = [
        _section_id(section) or "unknown"
        for section in sections
        if len(_section_evidence_refs(section)) < min_refs_per_section
    ]
    return RuleResult(
        rule_id="rule_deep_sections_cite_evidence",
        passed=bool(sections) and not under_cited_sections,
        severity="blocking",
        reject_to="writer",
        message=(
            "Every deep report section must cite collected evidence "
            f"(min_refs_per_section={min_refs_per_section}, under_cited={under_cited_sections})."
        ),
    )


# Sections where a buyer cannot trust third-party summaries alone — at least one
# cited source must come from the vendor itself (R10).
_OFFICIAL_REQUIRED_SECTION_KEYWORDS: tuple[str, ...] = (
    "pricing",
    "enterprise",
    "compliance",
    "security",
)


def _evidence_authority_by_id(evidence_items: list[EvidenceRecord]) -> dict[str, str]:
    authority_by_id: dict[str, str] = {}
    for item in evidence_items:
        span = item.span if isinstance(item.span, dict) else {}
        authority_raw = span.get("source_authority")
        authority_by_id[item.id] = (
            authority_raw if isinstance(authority_raw, str) else "third_party"
        )
    return authority_by_id


def rule_buyer_critical_sections_need_official_source(
    *,
    content_json: dict[str, object],
    evidence_items: list[EvidenceRecord],
) -> RuleResult:
    authority_by_id = _evidence_authority_by_id(evidence_items)
    flagged: list[str] = []
    for section in _iter_report_sections(content_json):
        section_id = _section_id(section)
        if section_id is None:
            continue
        lowered = section_id.lower()
        if not any(keyword in lowered for keyword in _OFFICIAL_REQUIRED_SECTION_KEYWORDS):
            continue
        refs = _section_evidence_refs(section)
        if not refs:
            # Missing citations are covered by the citation rules; this gate only
            # judges the authority of sources that ARE cited.
            continue
        if not any(authority_by_id.get(ref) == "official" for ref in refs):
            flagged.append(section_id)
    return RuleResult(
        rule_id="rule_buyer_critical_sections_need_official_source",
        passed=not flagged,
        severity="warning",
        reject_to="researcher",
        message=(
            "Buyer-critical sections should cite at least one official (vendor) source; "
            f"sections relying only on third-party evidence: {flagged}."
        ),
    )


def evaluate_fast_path_rules(
    *,
    content_markdown: str,
    content_json: dict[str, object],
    evidence_items: list[EvidenceRecord],
    allowed_evidence_ids: set[str],
    report_depth: Literal["quick", "deep"] = "quick",
    target_sections: list[str] | None = None,
) -> list[RuleResult]:
    rule_results = [
        rule_report_must_have_markdown_content(content_markdown),
        rule_report_template_id_present(content_json),
        rule_report_must_have_at_least_one_section(content_json),
        rule_report_section_count_in_bounds(content_json),
        rule_writer_sections_must_have_content(content_json),
        rule_writer_must_cite_evidence(
            content_json=content_json,
            allowed_evidence_ids=allowed_evidence_ids,
        ),
        rule_writer_no_fallback_mode(content_json),
        rule_evidence_must_be_desensitized(evidence_items),
        rule_buyer_critical_sections_need_official_source(
            content_json=content_json,
            evidence_items=evidence_items,
        ),
    ]
    if report_depth == "deep":
        rule_results.extend(
            [
                rule_deep_report_min_char_count(content_markdown=content_markdown),
                rule_deep_report_covers_target_sections(
                    content_json=content_json,
                    target_sections=target_sections,
                ),
                rule_deep_sections_min_chars(content_json=content_json),
                rule_deep_sections_cite_evidence(content_json=content_json),
            ]
        )
    return rule_results
