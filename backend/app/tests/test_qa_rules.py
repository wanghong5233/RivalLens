from __future__ import annotations

from datetime import datetime, timezone

from models.evidence import EvidenceRecord
from models.run import Run
from models.step import Step
from schemas.qa import Approval, Rejection
from service.llm.response import LLMResponse
from service.qa.engine import (
    _apply_numeric_claim_gate,
    _build_qa_fast_path_log_fields,
    _build_qa_slow_path_log_fields,
    _target_sections_for_report,
    build_qa_outcome,
)
from service.qa.rules import (
    RuleResult,
    evaluate_fast_path_rules,
    rule_evidence_must_be_desensitized,
    rule_deep_report_min_char_count,
    rule_report_must_have_at_least_one_section,
    rule_report_must_have_markdown_content,
    rule_report_section_count_in_bounds,
    rule_report_template_id_present,
    rule_writer_must_cite_evidence,
    rule_writer_no_fallback_mode,
    rule_writer_sections_must_have_content,
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


def test_rule_report_template_id_present_pass_and_fail() -> None:
    assert rule_report_template_id_present(content_json={"template_id": "battlecard_default"}).passed is True
    assert rule_report_template_id_present(content_json={"template_id": "   "}).passed is False


def test_rule_report_must_have_at_least_one_section_pass_and_fail() -> None:
    assert rule_report_must_have_at_least_one_section({"sections": ["feature"]}).passed is True
    assert rule_report_must_have_at_least_one_section({"sections": []}).passed is False


def test_rule_report_section_count_in_bounds() -> None:
    assert rule_report_section_count_in_bounds({"sections": [{"section_id": "feature"}]}).passed is True
    assert rule_report_section_count_in_bounds({"sections": []}).passed is False
    assert rule_report_section_count_in_bounds({"sections": [{} for _ in range(13)]}).passed is False


def test_rule_writer_sections_must_have_content_pass_and_fail() -> None:
    passing_content_json = {
        "sections": [
            {
                "section_id": "feature",
                "title": "Feature Comparison",
                "content_markdown": (
                    "This section contains enough concrete analysis details and evidence-backed "
                    "narrative to satisfy QA minimum length constraints."
                ),
                "evidence_refs": ["ev_test_001"],
            }
        ]
    }
    failing_content_json = {
        "sections": [
            {
                "section_id": "feature",
                "title": "Feature Comparison",
                "content_markdown": "too short",
                "evidence_refs": ["ev_test_001"],
            }
        ]
    }
    assert rule_writer_sections_must_have_content(passing_content_json).passed is True
    assert rule_writer_sections_must_have_content(failing_content_json).passed is False


def test_rule_writer_must_cite_evidence_pass_and_fail() -> None:
    passing_content_json = {
        "sections": [
            {
                "section_id": "feature",
                "title": "Feature Comparison",
                "content_markdown": "x" * 80,
                "evidence_refs": ["ev_test_001"],
            }
        ]
    }
    failing_content_json = {
        "sections": [
            {
                "section_id": "feature",
                "title": "Feature Comparison",
                "content_markdown": "x" * 80,
                "evidence_refs": ["ev_not_exists"],
            }
        ]
    }
    assert (
        rule_writer_must_cite_evidence(
            content_json=passing_content_json,
            allowed_evidence_ids={"ev_test_001"},
        ).passed
        is True
    )
    assert (
        rule_writer_must_cite_evidence(
            content_json=failing_content_json,
            allowed_evidence_ids={"ev_test_001"},
        ).passed
        is False
    )


def test_rule_evidence_must_be_desensitized_pass_and_fail() -> None:
    assert rule_evidence_must_be_desensitized([_make_evidence(desensitized=True)]).passed is True
    assert rule_evidence_must_be_desensitized([_make_evidence(desensitized=False)]).passed is False


def test_rule_writer_no_fallback_mode_pass_and_fail() -> None:
    assert rule_writer_no_fallback_mode({"risk_callouts": []}).passed is True
    assert rule_writer_no_fallback_mode({"risk_callouts": ["writer_fallback_mode"]}).passed is False
    assert rule_writer_no_fallback_mode({"risk_callouts": ["pricing volatility"]}).passed is True


def test_deep_report_min_char_count_blocks_short_baseline() -> None:
    result = rule_deep_report_min_char_count(content_markdown="x" * 2086)
    assert result.passed is False
    assert result.severity == "blocking"


def test_evaluate_fast_path_rules_applies_deep_only_gates() -> None:
    content_json = {
        "template_id": "default",
        "sections": [
            {
                "section_id": "pricing",
                "title": "Pricing",
                "content_markdown": "x" * 240,
                "evidence_refs": ["ev_test_001"],
            }
        ],
    }
    evidence = _make_evidence(desensitized=True)

    quick_results = evaluate_fast_path_rules(
        content_markdown="x" * 500,
        content_json=content_json,
        evidence_items=[evidence],
        allowed_evidence_ids={"ev_test_001"},
        report_depth="quick",
        target_sections=["pricing", "security"],
    )
    deep_results = evaluate_fast_path_rules(
        content_markdown="x" * 500,
        content_json=content_json,
        evidence_items=[evidence],
        allowed_evidence_ids={"ev_test_001"},
        report_depth="deep",
        target_sections=["pricing", "security"],
    )

    assert all(not item.rule_id.startswith("rule_deep_") for item in quick_results)
    failed_deep_rule_ids = {item.rule_id for item in deep_results if not item.passed}
    assert "rule_deep_report_min_char_count" in failed_deep_rule_ids
    assert "rule_deep_report_covers_target_sections" in failed_deep_rule_ids


def test_target_sections_prefers_writer_resolved_targets_over_plan_and_intake() -> None:
    run = Run(
        run_id="run_qa_targets",
        user_query="qa targets",
        status="completed",
        target_roles=["pm"],
        competitors=["comp_a"],
        intake_draft={"focus_dimensions": ["phantom_6", "phantom_7", "phantom_8", "phantom_9"]},
        plan_tree={
            "tasks": [
                {
                    "stage": "research",
                    "focus_dimensions": ["feature", "pricing", "security", "support"],
                }
            ]
        },
    )
    writer_step = Step(
        step_id="step_writer_targets",
        run_id=run.run_id,
        agent_name="writer",
        status="completed",
        retry_count=0,
        payload={
            "sections": [],
            "target_sections": ["feature", "pricing", "security", "support", "implementation"],
        },
    )

    assert _target_sections_for_report(run=run, writer_step=writer_step) == [
        "feature",
        "pricing",
        "security",
        "support",
        "implementation",
    ]


def test_target_sections_falls_back_to_plan_and_intake_without_writer_targets() -> None:
    run = Run(
        run_id="run_qa_targets_fallback",
        user_query="qa targets",
        status="completed",
        target_roles=["pm"],
        competitors=["comp_a"],
        intake_draft={"focus_dimensions": ["pricing"]},
        plan_tree={
            "tasks": [
                {
                    "stage": "research",
                    "focus_dimensions": ["feature"],
                }
            ]
        },
    )
    writer_step = Step(
        step_id="step_writer_targets_fallback",
        run_id=run.run_id,
        agent_name="writer",
        status="completed",
        retry_count=0,
        payload={"sections": ["security"]},
    )

    assert _target_sections_for_report(run=run, writer_step=writer_step) == [
        "security",
        "feature",
        "pricing",
    ]


def test_numeric_claim_gate_blocks_first_round_and_warns_after_retry() -> None:
    semantic_output = {
        "semantic_audit_passed": True,
        "reject_to": "writer",
        "severity": "warning",
        "finding": "Looks fine.",
        "required_fields": [],
        "unsupported_numeric_claims": [
            {
                "claim": "效率提升 28%",
                "section_id": "efficiency",
                "reason": "Evidence does not mention 28%.",
            }
        ],
    }

    first_round = _apply_numeric_claim_gate(
        semantic_output=semantic_output,
        qa_rejection_count=0,
        has_blocking_failures_pre_semantic=False,
    )
    retry_round = _apply_numeric_claim_gate(
        semantic_output=semantic_output,
        qa_rejection_count=1,
        has_blocking_failures_pre_semantic=False,
    )

    assert first_round["semantic_audit_passed"] is False
    assert first_round["severity"] == "blocking"
    assert first_round["reject_to"] == "writer"
    assert "reports.content_json.sections[].evidence_refs" in first_round["required_fields"]
    assert retry_round["semantic_audit_passed"] is True
    assert retry_round["severity"] == "warning"


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


def test_build_qa_fast_path_log_fields_surfaces_rule_ids_and_promoted_counts() -> None:
    rule_results = [
        RuleResult(
            rule_id="rule_writer_must_cite_evidence",
            passed=False,
            severity="blocking",
            reject_to="writer",
            message="missing evidence",
        ),
        RuleResult(
            rule_id="rule_writer_no_fallback_mode",
            passed=True,
            severity="blocking",
            reject_to="writer",
            message="ok",
        ),
    ]

    fields = _build_qa_fast_path_log_fields(
        mode="applied",
        rule_results=rule_results,
        promoted_qa_rule_ids=["rule_pricing"],
        promoted_rule_metadata={
            "promoted_qa_enforced_count": 1,
            "promoted_qa_parse_error_count": 0,
            "promoted_qa_blocked_rule_ids": ["rule_promoted_rule_pricing"],
        },
    )

    assert fields["failed_rule_ids"] == ["rule_writer_must_cite_evidence"]
    assert fields["blocking_failed_rule_ids"] == ["rule_writer_must_cite_evidence"]
    assert fields["promoted_qa_rule_ids"] == ["rule_pricing"]
    assert fields["promoted_qa_blocked_rule_ids"] == ["rule_promoted_rule_pricing"]
    assert fields["promoted_qa_enforced_count"] == 1
    assert fields["promoted_qa_parse_error_count"] == 0


def test_build_qa_slow_path_log_fields_surfaces_semantic_preview() -> None:
    rule_results = [
        RuleResult(
            rule_id="rule_qa_semantic_audit",
            passed=False,
            severity="blocking",
            reject_to="writer",
            message="semantic issue",
        )
    ]
    response = LLMResponse(
        model_slot="qa",
        provider="fake",
        model_name="fake-qa",
        prompt_preview="preview",
        prompt_hash="hash",
        content={},
        prompt_tokens=1,
        completion_tokens=1,
        latency_ms=1,
        error=None,
        fallback_used=False,
    )

    fields = _build_qa_slow_path_log_fields(
        mode="applied",
        rule_results=rule_results,
        semantic_output={
            "semantic_audit_passed": False,
            "finding": "x" * 350,
            "reject_to": "writer",
            "severity": "blocking",
        },
        semantic_response=response,
        schema_error="finding is required",
    )

    assert fields["failed_rule_ids"] == ["rule_qa_semantic_audit"]
    assert fields["semantic_finding_preview"] == "x" * 300
    assert fields["semantic_reject_to"] == "writer"
    assert fields["semantic_severity"] == "blocking"
    assert fields["schema_error"] == "finding is required"


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
            rule_id="rule_report_template_id_present",
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
