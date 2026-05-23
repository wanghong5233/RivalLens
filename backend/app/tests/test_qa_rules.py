from __future__ import annotations

from datetime import datetime, timezone

from models.evidence import EvidenceRecord
from schemas.qa import Approval, Rejection
from service.qa.engine import build_qa_outcome
from service.qa.rules import (
    RuleResult,
    rule_evidence_must_be_desensitized,
    rule_report_must_have_at_least_one_section,
    rule_report_must_have_markdown_content,
    rule_report_template_id_valid,
)


def _make_evidence(*, desensitized: bool) -> EvidenceRecord:
    return EvidenceRecord(
        id="ev_test_001",
        run_id="run_test_001",
        source_type="official_site",
        source_url="https://example.com",
        source_title="Example",
        quote="quoted text",
        sanitized_text="sanitized text",
        span={"start": 0, "end": 1},
        collected_by="step_researcher_001",
        collected_at=datetime.now(timezone.utc),
        desensitized=desensitized,
    )


def test_rule_report_must_have_markdown_content_pass_and_fail() -> None:
    assert rule_report_must_have_markdown_content("# title").passed is True
    assert rule_report_must_have_markdown_content("  ").passed is False


def test_rule_report_template_id_valid_pass_and_fail() -> None:
    assert rule_report_template_id_valid(content_json={"template_id": "battlecard_default"}).passed is True
    assert rule_report_template_id_valid(content_json={"template_id": "invalid_template"}).passed is False


def test_rule_report_must_have_at_least_one_section_pass_and_fail() -> None:
    assert rule_report_must_have_at_least_one_section({"sections": ["feature"]}).passed is True
    assert rule_report_must_have_at_least_one_section({"sections": []}).passed is False


def test_rule_evidence_must_be_desensitized_pass_and_fail() -> None:
    assert rule_evidence_must_be_desensitized([_make_evidence(desensitized=True)]).passed is True
    assert rule_evidence_must_be_desensitized([_make_evidence(desensitized=False)]).passed is False


def test_engine_aggregation_rejects_when_blocking_failed() -> None:
    rule_results = [
        RuleResult(
            rule_id="rule_report_must_have_markdown_content",
            passed=False,
            severity="blocking",
            reject_to="writer",
            message="markdown missing",
        )
    ]
    result = build_qa_outcome(
        target_step_id="step_writer_001",
        reviewer_step_id="step_qa_001",
        rule_results=rule_results,
        qa_rejection_count=0,
    )
    assert isinstance(result, Rejection)
    assert result.reject_to == "writer"
    assert "rule_report_must_have_markdown_content" in result.failed_rule_ids


def test_engine_aggregation_approves_when_all_rules_pass() -> None:
    rule_results = [
        RuleResult(
            rule_id="rule_report_must_have_markdown_content",
            passed=True,
            severity="blocking",
            reject_to="writer",
            message="ok",
        ),
        RuleResult(
            rule_id="rule_report_template_id_valid",
            passed=True,
            severity="blocking",
            reject_to="writer",
            message="ok",
        ),
        RuleResult(
            rule_id="rule_report_must_have_at_least_one_section",
            passed=True,
            severity="blocking",
            reject_to="writer",
            message="ok",
        ),
        RuleResult(
            rule_id="rule_evidence_must_be_desensitized",
            passed=True,
            severity="blocking",
            reject_to="researcher",
            message="ok",
        ),
    ]
    result = build_qa_outcome(
        target_step_id="step_writer_001",
        reviewer_step_id="step_qa_001",
        rule_results=rule_results,
        qa_rejection_count=0,
    )
    assert isinstance(result, Approval)
    assert result.semantic_audit_passed is True
    assert len(result.passed_rule_ids) == 4
