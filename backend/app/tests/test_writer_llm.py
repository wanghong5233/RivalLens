from __future__ import annotations

from agents.nodes.writer import (
    _build_fallback_report,
    _render_report_markdown,
)
from schemas.agent_outputs import (
    AnalystOutput,
    WriterExecutionContext,
    WriterReportOutput,
    resolve_writer_target_sections,
)
from service.llm.prompts import (
    WRITER_SYSTEM_PROMPT,
    build_writer_fallback_user_prompt,
    build_writer_user_prompt,
)


def test_build_writer_prompts_include_required_context() -> None:
    user_prompt = build_writer_user_prompt(
        user_query="compare cursor and windsurf",
        template_id="battlecard_default",
        target_sections=["feature", "pricing"],
        requested_sections=["feature", "pricing"],
        competitors=["comp_cursor", "comp_windsurf"],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "feature",
                "competitor_id": "comp_cursor",
                "quote_preview": "repository context indexing",
                "source_title": "Cursor Docs",
                "source_url": "https://cursor.com",
            }
        ],
        allowed_evidence_ids=["ev_001"],
        analyst_summary="Cursor leads in feature depth.",
        analyst_insights=[
            {
                "insight_id": "insight_1",
                "dimension": "feature",
                "finding": "Cursor provides stronger repo-level context.",
                "confidence": "high",
                "evidence_ids": ["ev_001"],
            }
        ],
        risk_flags=["pricing volatility"],
        recommended_sections=["feature", "pricing"],
        qa_reasons=["Unsupported numeric claims."],
        unsupported_numeric_claims=[{"claim": "$40/seat", "section_id": "pricing"}],
    )
    fallback_prompt = build_writer_fallback_user_prompt(
        template_id="battlecard_default",
        requested_sections=["feature"],
        evidence_ids=["ev_001"],
        analyst_summary="Cursor leads in feature depth.",
    )

    assert "Writer context" in user_prompt
    assert "- evidence_briefs:" in user_prompt
    assert "- analyst_insights:" in user_prompt
    assert "- allowed_evidence_ids:" in user_prompt
    assert "- target_sections:" in user_prompt
    assert "- report_depth: quick" in user_prompt
    assert "[ev_xxx]" in user_prompt
    assert "never output bare ev_xxx or insight_x ids in markdown" in user_prompt
    assert "unsupported_numeric_claims" in user_prompt
    assert "$40/seat" in user_prompt
    assert "[ev_xxx]" in WRITER_SYSTEM_PROMPT
    assert "Never emit bare ev_xxx ids" in WRITER_SYSTEM_PROMPT
    assert "Exact numbers" in WRITER_SYSTEM_PROMPT
    assert "During QA rewrites" in WRITER_SYSTEM_PROMPT
    assert "Fallback writer request" in fallback_prompt
    assert "- evidence_ids:" in fallback_prompt


def test_writer_report_output_accepts_valid_payload() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["feature"],
        allowed_evidence_ids=frozenset({"ev_001"}),
        allowed_insight_ids=frozenset({"insight_1"}),
    )
    result = WriterReportOutput.parse_llm_content(
        {
            "template_id": "battlecard_default",
            "title": "RivalLens Battlecard",
            "executive_summary": "This summary is long enough and grounded by evidence references.",
            "sections": [
                {
                    "section_id": "feature",
                    "title": "Feature Comparison",
                    "content_markdown": (
                        "Cursor delivers stronger repository-level context management while preserving "
                        "developer iteration speed and minimizing repetitive prompt overhead."
                    ),
                    "evidence_refs": ["ev_001"],
                    "insight_refs": ["insight_1"],
                }
            ],
            "risk_callouts": ["pricing volatility"],
        },
        execution_context=context,
    )

    report = result.to_report_content()
    assert report["template_id"] == "battlecard_default"
    assert len(report["sections"]) == 1
    assert report["sections"][0]["evidence_refs"] == ["ev_001"]


def test_writer_report_output_counts_top_level_executive_summary_as_covered() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["executive_summary", "feature"],
        allowed_evidence_ids=frozenset({"ev_001"}),
        allowed_insight_ids=frozenset({"insight_1"}),
    )
    result = WriterReportOutput.parse_llm_content(
        {
            "template_id": "battlecard_default",
            "title": "RivalLens Battlecard",
            "executive_summary": "This summary is present and should cover the executive_summary target.",
            "sections": [
                {
                    "section_id": "feature",
                    "title": "Feature Comparison",
                    "content_markdown": (
                        "Feature analysis contains enough detail and cites grounded evidence."
                    ),
                    "evidence_refs": ["ev_001"],
                    "insight_refs": ["insight_1"],
                }
            ],
            "risk_callouts": [],
        },
        execution_context=context,
    )

    assert "uncovered_section:executive_summary" not in result.risk_callouts


def test_writer_report_output_rejects_invalid_evidence_refs() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["feature"],
        allowed_evidence_ids=frozenset({"ev_001"}),
        allowed_insight_ids=frozenset({"insight_1"}),
    )
    try:
        WriterReportOutput.parse_llm_content(
            {
                "template_id": "battlecard_default",
                "title": "RivalLens Battlecard",
                "executive_summary": "This summary is long enough and grounded by evidence references.",
                "sections": [
                    {
                        "section_id": "feature",
                        "title": "Feature Comparison",
                        "content_markdown": (
                            "Feature analysis contains enough detail to satisfy QA validation but "
                            "uses an invalid evidence id."
                        ),
                        "evidence_refs": ["ev_missing"],
                        "insight_refs": ["insight_1"],
                    }
                ],
                "risk_callouts": ["pricing volatility"],
            },
            execution_context=context,
        )
        raised = False
    except ValueError:
        raised = True

    assert raised


def test_fallback_report_render_contains_evidence_citations() -> None:
    report_content = _build_fallback_report(
        template_id="battlecard_default",
        target_sections=["feature", "pricing"],
        evidence_ids=["ev_001", "ev_002"],
        analyst_summary="Cursor leads in feature depth.",
        insight_briefs=[
            {
                "insight_id": "insight_1",
                "dimension": "feature",
                "finding": "Cursor provides stronger repo-level context.",
                "confidence": "high",
                "evidence_ids": ["ev_001"],
            }
        ],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "feature",
                "competitor_id": "comp_cursor",
                "quote_preview": "repository context indexing",
                "source_title": "Cursor Docs",
                "source_url": "https://cursor.com",
            }
        ],
        risk_flags=["pricing volatility"],
    )
    markdown = _render_report_markdown(
        report_content,
        allowed_evidence_ids={"ev_001", "ev_002"},
    )

    assert "[ev_001]" in markdown
    assert "## Feature" in markdown or "Feature" in markdown


def test_report_markdown_sanitizes_internal_ids() -> None:
    report_content = {
        "title": "RivalLens Battlecard",
        "executive_summary": "Summary cites ev_001 and drops ev_missing plus insight_9.",
        "sections": [
            {
                "title": "Feature",
                "content_markdown": (
                    "Cursor leads on context ev_001 and already cites [ev_002]. "
                    "Drop hallucinated ev_fake and internal insight_1."
                ),
                "evidence_refs": ["ev_001", "ev_fake"],
                "insight_refs": ["insight_1"],
            }
        ],
        "risk_callouts": ["Risk tied to ev_002 and not insight_2."],
    }

    markdown = _render_report_markdown(
        report_content,
        allowed_evidence_ids={"ev_001", "ev_002"},
    )

    assert "[ev_001]" in markdown
    assert "[ev_002]" in markdown
    assert "Evidence: [ev_001]" in markdown
    assert "Evidence: [ev_001], [ev_fake]" not in markdown
    assert "ev_fake" not in markdown
    assert "ev_missing" not in markdown
    assert "Insights:" not in markdown
    assert "insight_" not in markdown
    assert " ev_001" not in markdown
    assert " ev_002" not in markdown


def test_fallback_report_sections_follow_target_sections() -> None:
    report_content = _build_fallback_report(
        template_id="battlecard_default",
        target_sections=["feature", "pricing"],
        evidence_ids=["ev_001", "ev_002", "ev_003"],
        analyst_summary="Summary.",
        insight_briefs=[],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "feature",
                "competitor_id": "comp_a",
                "quote_preview": "quote",
                "source_title": "title",
                "source_url": "https://example.com",
            }
        ],
        risk_flags=[],
    )

    section_ids = [section["section_id"] for section in report_content["sections"]]
    assert section_ids == ["feature", "pricing"]
    pricing_section = report_content["sections"][1]
    assert pricing_section["evidence_refs"] == []
    assert "uncovered_section:pricing" in report_content["risk_callouts"]


def test_fallback_report_does_not_round_robin_unmatched_insights_or_evidence() -> None:
    report_content = _build_fallback_report(
        template_id="battlecard_default",
        target_sections=["pricing"],
        evidence_ids=["ev_001"],
        analyst_summary="Summary.",
        insight_briefs=[
            {
                "insight_id": "insight_1",
                "dimension": "feature",
                "finding": "Feature depth is stronger.",
                "confidence": "high",
                "evidence_ids": ["ev_001"],
            }
        ],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "feature",
                "competitor_id": "comp_a",
                "quote_preview": "feature quote",
                "source_title": "title",
                "source_url": "https://example.com",
            }
        ],
        risk_flags=[],
    )

    section = report_content["sections"][0]
    assert section["section_id"] == "pricing"
    assert section["evidence_refs"] == []
    assert section["insight_refs"] == []
    assert "uncovered_section:pricing" in report_content["risk_callouts"]


def test_fallback_report_handles_empty_target_sections_without_name_error() -> None:
    report_content = _build_fallback_report(
        template_id=None,
        target_sections=[],
        evidence_ids=["ev_001"],
        analyst_summary="Summary.",
        insight_briefs=[],
        evidence_briefs=[],
        risk_flags=[],
    )

    assert report_content["sections"][0]["section_id"] == "general"
    assert report_content["sections"][0]["evidence_refs"] == []
    assert "uncovered_section:general" in report_content["risk_callouts"]


def test_writer_report_output_allows_template_auto_mode() -> None:
    context = WriterExecutionContext(
        template_id=None,
        target_sections=["go_to_market"],
        allowed_evidence_ids=frozenset({"ev_001"}),
        allowed_insight_ids=frozenset(),
    )
    result = WriterReportOutput.parse_llm_content(
        {
            "template_id": "default",
            "title": "Universal Report",
            "executive_summary": "Valid summary with evidence references.",
            "sections": [
                {
                    "section_id": "go_to_market",
                    "title": "Go To Market",
                    "content_markdown": (
                        "This section has enough detail and valid evidence references to pass "
                        "writer normalization under dynamic section mode."
                    ),
                    "evidence_refs": ["ev_001"],
                    "insight_refs": [],
                }
            ],
            "risk_callouts": [],
        },
        execution_context=context,
    )

    report = result.to_report_content()
    assert report["template_id"] == "default"
    assert report["sections"][0]["section_id"] == "go_to_market"


def test_analyst_output_derives_sections_from_insights() -> None:
    output = AnalystOutput.model_validate(
        {
            "summary": "Analyst summary with enough context.",
            "insights": [
                {
                    "dimension": "competitive_edge",
                    "finding": "Product A leads on context depth.",
                    "evidence_ids": ["ev_001"],
                    "confidence": "high",
                },
                {
                    "dimension": "monetization_model",
                    "finding": "Subscription tiers vary widely.",
                    "evidence_ids": ["ev_002"],
                    "confidence": "medium",
                },
            ],
            "risk_flags": ["pricing volatility"],
            "recommended_sections": [
                "Competitive positioning gap analysis report",
                "Monetization model benchmarking comparison",
            ],
        }
    )

    assert output.recommended_sections == ["competitive_edge", "monetization_model"]


def test_resolve_writer_target_sections_uses_insight_derived_recommendations() -> None:
    targets = resolve_writer_target_sections(
        requested_sections=None,
        recommended_sections=["competitive_edge", "monetization_model"],
    )

    assert targets == ["competitive_edge", "monetization_model"]
