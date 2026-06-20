from __future__ import annotations

from agents.nodes.writer import (
    _apply_structured_writer_sections,
    _apply_numeric_claim_guardrail,
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
        analyst_comparisons=[
            {
                "dimension": "feature",
                "cells": [
                    {
                        "competitor_id": "comp_cursor",
                        "stance": "leader",
                        "summary": "Cursor provides stronger repo-level context.",
                        "confidence": "high",
                        "evidence_ids": ["ev_001"],
                    }
                ],
            }
        ],
        risk_flags=["pricing volatility"],
        recommended_sections=["feature", "pricing"],
        qa_reasons=["Unsupported numeric claims."],
        unsupported_numeric_claims=[{"claim": "$40/seat", "section_id": "pricing"}],
        analysis_intent="对比企业版能力和定价",
        market_scope="中国市场",
        response_language="zh",
    )
    fallback_prompt = build_writer_fallback_user_prompt(
        template_id="battlecard_default",
        requested_sections=["feature"],
        evidence_ids=["ev_001"],
        analyst_summary="Cursor leads in feature depth.",
        user_query="compare cursor and windsurf",
        response_language="zh",
        report_depth="deep",
    )

    assert "Writer context" in user_prompt
    assert "- evidence_briefs:" in user_prompt
    assert "- analyst_insights:" in user_prompt
    assert "- analyst_comparisons:" in user_prompt
    assert "- allowed_evidence_ids:" in user_prompt
    assert "- target_sections:" in user_prompt
    assert "- analysis_intent: 对比企业版能力和定价" in user_prompt
    assert "- market_scope: 中国市场" in user_prompt
    assert "- response_language: zh" in user_prompt
    assert "- report_depth: quick" in user_prompt
    assert "[ev_xxx]" in user_prompt
    assert "never output bare ev_xxx or insight_x ids in markdown" in user_prompt
    assert "unsupported_numeric_claims" in user_prompt
    assert "$40/seat" in user_prompt
    assert "Do not create a section titled Executive Summary or 执行摘要" in user_prompt
    assert "[ev_xxx]" in WRITER_SYSTEM_PROMPT
    assert "Never emit bare ev_xxx ids" in WRITER_SYSTEM_PROMPT
    assert "Write all report output in response_language" in WRITER_SYSTEM_PROMPT
    assert "Exact numbers" in WRITER_SYSTEM_PROMPT
    assert "During QA rewrites" in WRITER_SYSTEM_PROMPT
    assert "Fallback writer request" in fallback_prompt
    assert "- allowed_evidence_ids:" in fallback_prompt
    # The degraded path used to drop response_language and emit ungrounded English;
    # guard that it now carries language + grounding so a transport blip cannot
    # silently flip a zh report to English boilerplate.
    assert "- response_language: zh" in fallback_prompt
    assert "- user_query: compare cursor and windsurf" in fallback_prompt
    assert "- report_depth: deep" in fallback_prompt
    assert "Write the report in response_language" in fallback_prompt


def test_writer_report_output_accepts_valid_payload() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["feature"],
        renderable_sections=["feature"],
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


def test_numeric_claim_guardrail_downgrades_section_numbers() -> None:
    report_content = {
        "template_id": "default",
        "title": "测试报告",
        "executive_summary": "摘要。",
        "sections": [
            {
                "section_id": "pricing_strategy",
                "title": "定价策略",
                "content_markdown": "旗舰版定价 3799 元，入门版 1899 元，预测区间 1500-2000 元。",
                "evidence_refs": ["ev_001"],
                "insight_refs": [],
            },
            {
                "section_id": "product_positioning",
                "title": "定位",
                "content_markdown": "定位强调生态整合能力。",
                "evidence_refs": ["ev_002"],
                "insight_refs": [],
            },
        ],
        "risk_callouts": [],
    }
    updated, downgraded_sections = _apply_numeric_claim_guardrail(
        report_content=report_content,
        unsupported_numeric_claims=[
            {
                "claim": "预测区间 1500-2000 元",
                "section_id": "pricing_strategy",
                "reason": "unsupported",
            }
        ],
        response_language="zh",
    )

    assert downgraded_sections == ["pricing_strategy"]
    pricing_section = updated["sections"][0]
    assert isinstance(pricing_section, dict)
    pricing_markdown = pricing_section["content_markdown"]
    assert isinstance(pricing_markdown, str)
    assert "3799" not in pricing_markdown
    assert "1899" not in pricing_markdown
    assert "1500" not in pricing_markdown
    assert "2000" not in pricing_markdown
    assert "若干" in pricing_markdown
    assert "numeric_claims_downgraded:pricing_strategy" in updated["risk_callouts"]
    positioning_section = updated["sections"][1]
    assert isinstance(positioning_section, dict)
    assert positioning_section["content_markdown"] == "定位强调生态整合能力。"


def test_writer_report_output_counts_top_level_executive_summary_as_covered() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["executive_summary", "feature"],
        renderable_sections=["executive_summary", "feature"],
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
        renderable_sections=["feature"],
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


def test_report_markdown_localizes_fixed_labels_for_chinese_output() -> None:
    report_content = {
        "title": "国内销售 AI 工具对比",
        "executive_summary": "适合线下拜访团队的工具需要覆盖线索、跟进和邮件协同。",
        "sections": [
            {
                "title": "选型建议",
                "content_markdown": "优先选择能绑定销售流程证据的工具 [ev_001]。",
                "evidence_refs": ["ev_001"],
                "insight_refs": [],
            }
        ],
        "risk_callouts": ["国内可用性需要复核 [ev_001]"],
    }

    markdown = _render_report_markdown(
        report_content,
        allowed_evidence_ids={"ev_001"},
        response_language="zh",
    )

    assert "## 执行摘要" in markdown
    assert "证据: [ev_001]" in markdown
    assert "## 风险提示" in markdown
    assert "## Executive Summary" not in markdown
    assert "Evidence:" not in markdown
    assert "## Risk Callouts" not in markdown


def test_report_markdown_deduplicates_executive_summary_sections() -> None:
    report_content = {
        "title": "测试报告",
        "executive_summary": "顶层执行摘要内容。",
        "sections": [
            {
                "title": "执行摘要：赛道机会与核心结论",
                "content_markdown": "这段应该被跳过。",
                "evidence_refs": [],
                "insight_refs": [],
            },
            {
                "title": "核心发现",
                "content_markdown": "保留的正文内容。",
                "evidence_refs": ["ev_001"],
                "insight_refs": [],
            },
        ],
        "risk_callouts": [],
    }

    markdown = _render_report_markdown(
        report_content,
        allowed_evidence_ids={"ev_001"},
        response_language="zh",
    )

    assert markdown.count("## 执行摘要") == 1
    assert "执行摘要：赛道机会与核心结论" not in markdown
    assert "## 核心发现" in markdown


def test_report_markdown_appends_methodology_section() -> None:
    report_content = {
        "title": "测试报告",
        "executive_summary": "摘要。",
        "sections": [],
        "risk_callouts": [],
    }

    markdown = _render_report_markdown(
        report_content,
        allowed_evidence_ids={"ev_001", "ev_002"},
        response_language="zh",
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "competitor_id": "厂商A",
                "source_authority": "official",
                "source_type": "pricing_page",
            },
            {
                "evidence_id": "ev_002",
                "competitor_id": "厂商B",
                "source_authority": "third_party",
                "source_type": "article",
            },
        ],
    )

    assert "## 数据来源与方法论" in markdown
    assert "覆盖竞品: 2 (厂商A, 厂商B)" in markdown
    assert "证据总数: 2" in markdown
    assert "来源等级分布: official: 1, third_party: 1" in markdown
    assert "来源类型分布: article: 1, pricing_page: 1" in markdown
    assert "数据缺口披露: 厂商B: 官方来源和定价页均未覆盖（仅第三方资料）" in markdown


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
        renderable_sections=["go_to_market"],
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

    assert targets == [
        "executive_summary",
        "competitor_profiles",
        "comparison_matrix",
        "positioning_map",
        "self_positioning",
        "strategic_recommendations",
    ]


def test_apply_structured_writer_sections_renders_triplet_matrix_and_profiles() -> None:
    updated = _apply_structured_writer_sections(
        report_content={
            "template_id": "default",
            "title": "RivalLens",
            "executive_summary": "summary",
            "sections": [
                {
                    "section_id": "trend_summary",
                    "title": "趋势综述",
                    "content_markdown": "趋势段落 [ev_001]",
                    "evidence_refs": ["ev_001"],
                    "insight_refs": [],
                }
            ],
            "risk_callouts": [],
        },
        target_sections=[
            "executive_summary",
            "competitor_profiles",
            "comparison_matrix",
            "positioning_map",
            "strategic_recommendations",
            "market_landscape_map",
            "trend_summary",
            "opportunity_map",
        ],
        analysis_archetype="landscape",
        response_language="zh",
        report_depth="quick",
        knowledge_payload={
            "schema_version": "schema_v0.2",
            "features": [
                {"competitor_id": "Meta", "name": "语音助手", "evidence_ids": ["ev_001"]},
                {"competitor_id": "XREAL", "name": "空间显示", "evidence_ids": ["ev_002"]},
            ],
            "pricings": [
                {"competitor_id": "Meta", "model": "subscription", "free_plan": False, "enterprise_plan": True, "evidence_ids": ["ev_001"]}
            ],
            "personas": [],
            "feedback": [
                {"competitor_id": "Meta", "sentiment": "positive", "topic": "续航", "summary": "续航较好", "evidence_ids": ["ev_003"]}
            ],
            "missing_reasons": {},
            "coverage": {
                "Meta": {"feature": "complete", "pricing": "complete", "feedback": "partial"},
                "XREAL": {"feature": "partial", "pricing": "insufficient_data", "feedback": "insufficient_data"},
            },
        },
        comparison_briefs=[],
        evidence_briefs=[
            {"evidence_id": "ev_001", "competitor_id": "Meta"},
            {"evidence_id": "ev_002", "competitor_id": "XREAL"},
            {"evidence_id": "ev_003", "competitor_id": "Meta"},
        ],
        allowed_evidence_ids={"ev_001", "ev_002", "ev_003"},
        state_competitors=["Meta", "XREAL"],
        discovered_competitor_sources={
            "Meta": {"candidate_role": "direct_competitor"},
            "XREAL": {"candidate_role": "adjacent_competitor"},
        },
        self_product=None,
        preserve_llm_executive_summary=False,
    )

    sections = [item for item in updated["sections"] if isinstance(item, dict)]
    section_ids = [item.get("section_id") for item in sections]
    assert "competitor_profiles" in section_ids
    assert "comparison_matrix" in section_ids
    assert "positioning_map" in section_ids
    assert "market_landscape_map" in section_ids
    matrix_section = next(item for item in sections if item.get("section_id") == "comparison_matrix")
    profile_section = next(item for item in sections if item.get("section_id") == "competitor_profiles")
    positioning_section = next(item for item in sections if item.get("section_id") == "positioning_map")
    assert "|竞品|核心功能摘要|覆盖状态|" in matrix_section["content_markdown"]
    assert "### Meta" in profile_section["content_markdown"]
    assert "领先梯队（能力深、商业化强）" in positioning_section["content_markdown"]
    assert "Q1" not in positioning_section["content_markdown"]
    # Fallback path (no LLM summary preserved) synthesizes the deterministic
    # positioning signal so positioning_map and executive_summary stay consistent.
    assert "领先梯队 Meta" in updated["executive_summary"]
    assert "观察梯队 XREAL" in updated["executive_summary"]


def test_apply_structured_writer_sections_preserves_llm_executive_summary() -> None:
    llm_summary = "Meta 在功能深度与商业化上同时领先，XREAL 仍处早期观察阶段。"
    updated = _apply_structured_writer_sections(
        report_content={
            "template_id": "default",
            "title": "RivalLens",
            "executive_summary": llm_summary,
            "sections": [],
            "risk_callouts": [],
        },
        target_sections=[
            "executive_summary",
            "competitor_profiles",
            "comparison_matrix",
            "positioning_map",
            "market_landscape_map",
            "trend_summary",
        ],
        analysis_archetype="landscape",
        response_language="zh",
        report_depth="quick",
        knowledge_payload={
            "schema_version": "schema_v0.2",
            "features": [
                {"competitor_id": "Meta", "name": "语音助手", "evidence_ids": ["ev_001"]},
            ],
            "pricings": [
                {"competitor_id": "Meta", "model": "subscription", "free_plan": False, "enterprise_plan": True, "evidence_ids": ["ev_001"]}
            ],
            "personas": [],
            "feedback": [
                {"competitor_id": "Meta", "sentiment": "positive", "topic": "续航", "summary": "续航较好", "evidence_ids": ["ev_003"]}
            ],
            "missing_reasons": {},
            "coverage": {
                "Meta": {"feature": "complete", "pricing": "complete", "feedback": "partial"},
            },
        },
        comparison_briefs=[],
        evidence_briefs=[
            {"evidence_id": "ev_001", "competitor_id": "Meta"},
            {"evidence_id": "ev_003", "competitor_id": "Meta"},
        ],
        allowed_evidence_ids={"ev_001", "ev_003"},
        state_competitors=["Meta", "XREAL"],
        discovered_competitor_sources={
            "Meta": {"candidate_role": "direct_competitor"},
            "XREAL": {"candidate_role": "adjacent_competitor"},
        },
        self_product=None,
        preserve_llm_executive_summary=True,
    )

    # Primary LLM narrative must survive untouched; positioning_map still renders
    # the deterministic clusters independently.
    assert updated["executive_summary"] == llm_summary
    positioning_section = next(
        item
        for item in updated["sections"]
        if isinstance(item, dict) and item.get("section_id") == "positioning_map"
    )
    assert "领先梯队（能力深、商业化强）" in positioning_section["content_markdown"]
