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
        risk_flags=["writer_fallback_mode"],
    )
    markdown = _render_report_markdown(report_content)

    assert report_content["sections"][0]["evidence_refs"] == ["ev_001"]
    assert "[ev_001]" in markdown
    assert "## Executive Summary" in markdown
