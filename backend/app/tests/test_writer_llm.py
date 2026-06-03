from __future__ import annotations

from agents.nodes.writer import (
    _build_fallback_report,
    _normalize_writer_output,
    _render_report_markdown,
)
from service.llm.prompts import build_writer_fallback_user_prompt, build_writer_user_prompt


def test_build_writer_prompts_include_required_context() -> None:
    user_prompt = build_writer_user_prompt(
        user_query="compare cursor and windsurf",
        template_id="battlecard_default",
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
    assert "- allowed_section_ids:" not in user_prompt
    assert "Fallback writer request" in fallback_prompt
    assert "- evidence_ids:" in fallback_prompt


def test_normalize_writer_output_accepts_valid_payload() -> None:
    result = _normalize_writer_output(
        content={
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
        template_id="battlecard_default",
        target_sections=["feature"],
        allowed_evidence_ids={"ev_001"},
        allowed_insight_ids={"insight_1"},
        default_risk_callouts=["fallback-risk"],
    )

    assert result is not None
    assert result["template_id"] == "battlecard_default"
    assert len(result["sections"]) == 1
    assert result["sections"][0]["evidence_refs"] == ["ev_001"]


def test_normalize_writer_output_rejects_invalid_evidence_refs() -> None:
    result = _normalize_writer_output(
        content={
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
        template_id="battlecard_default",
        target_sections=["feature"],
        allowed_evidence_ids={"ev_001"},
        allowed_insight_ids={"insight_1"},
        default_risk_callouts=[],
    )

    assert result is None


def test_fallback_report_render_contains_evidence_citations() -> None:
    report_content = _build_fallback_report(
        template_id="battlecard_default",
        target_sections=["feature"],
        evidence_ids=["ev_001"],
        analyst_summary="Fallback summary from analyst payload.",
        insight_briefs=[
            {
                "insight_id": "insight_1",
                "dimension": "feature",
                "finding": "Cursor keeps better repository context continuity.",
                "confidence": "high",
                "evidence_ids": ["ev_001"],
            }
        ],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "feature",
                "competitor_id": "Cursor",
                "quote_preview": "repository context indexing",
                "source_title": "Cursor Docs",
                "source_url": "https://cursor.com",
            }
        ],
        risk_flags=["writer_fallback_mode"],
    )
    markdown = _render_report_markdown(report_content)

    assert report_content["sections"][0]["evidence_refs"] == ["ev_001"]
    assert "[ev_001]" in markdown
    assert "## Executive Summary" in markdown


def test_fallback_report_sections_use_distinct_insights() -> None:
    report_content = _build_fallback_report(
        template_id="battlecard_default",
        target_sections=["pricing", "feature", "positioning"],
        evidence_ids=["ev_001", "ev_002", "ev_003"],
        analyst_summary="Summary",
        insight_briefs=[
            {
                "insight_id": "insight_pricing",
                "dimension": "pricing_model_details",
                "finding": "Pricing insight A.",
                "confidence": "high",
                "evidence_ids": ["ev_001"],
            },
            {
                "insight_id": "insight_feature",
                "dimension": "product_market_positioning",
                "finding": "Feature insight B.",
                "confidence": "medium",
                "evidence_ids": ["ev_002"],
            },
            {
                "insight_id": "insight_positioning",
                "dimension": "product_positioning",
                "finding": "Positioning insight C.",
                "confidence": "high",
                "evidence_ids": ["ev_003"],
            },
        ],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "pricing_model_details",
                "competitor_id": "Windsurf",
                "quote_preview": "pricing quote",
                "source_title": "",
                "source_url": "",
            },
            {
                "evidence_id": "ev_002",
                "dimension": "product_market_positioning",
                "competitor_id": "Cursor",
                "quote_preview": "feature quote",
                "source_title": "",
                "source_url": "",
            },
            {
                "evidence_id": "ev_003",
                "dimension": "product_positioning",
                "competitor_id": "Copilot",
                "quote_preview": "positioning quote",
                "source_title": "",
                "source_url": "",
            },
        ],
        risk_flags=["writer_fallback_mode"],
    )
    bodies = [section["content_markdown"] for section in report_content["sections"]]
    assert len(set(bodies)) == 3


def test_normalize_writer_output_allows_template_auto_mode() -> None:
    result = _normalize_writer_output(
        content={
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
        template_id=None,
        target_sections=["go_to_market"],
        allowed_evidence_ids={"ev_001"},
        allowed_insight_ids=set(),
        default_risk_callouts=[],
    )

    assert result is not None
    assert result["template_id"] == "default"
    assert result["sections"][0]["section_id"] == "go_to_market"
