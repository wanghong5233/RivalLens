from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.agent_outputs import (
    AnalystOutput,
    DiscoveryExtractOutput,
    IntakeTurnOutput,
    PlannerOutput,
    QASemanticOutput,
    ResearcherDecisionOutput,
    SupervisorToolCallOutput,
    WriterExecutionContext,
    WriterReportOutput,
    resolve_writer_target_sections,
)
from schemas.contracts import validate_dimension
from schemas.intake import RunIntakeDraft


def test_analyst_output_canonicalizes_recommended_sections_from_insights() -> None:
    output = AnalystOutput.model_validate(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "competitive_edge",
                    "finding": "Product A leads on context depth.",
                    "evidence_ids": ["ev_001"],
                    "confidence": "high",
                }
            ],
            "recommended_sections": ["Competitive positioning gap analysis report"],
        }
    )

    assert output.recommended_sections == ["competitive_edge"]


def test_resolve_writer_target_sections_prefers_analyst_dimensions() -> None:
    sections = resolve_writer_target_sections(
        requested_sections=None,
        recommended_sections=["competitive_edge", "monetization_model"],
    )

    assert sections == ["competitive_edge", "monetization_model"]


def test_writer_execution_context_aligns_with_analyst_output() -> None:
    analyst = AnalystOutput.model_validate(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "feature",
                    "finding": "Feature depth varies across competitors.",
                    "evidence_ids": ["ev_001"],
                    "confidence": "medium",
                }
            ],
            "recommended_sections": [],
        }
    )
    context = WriterExecutionContext.resolve(
        template_id="battlecard_default",
        requested_sections=None,
        analyst_output=analyst,
        allowed_evidence_ids={"ev_001"},
        allowed_insight_ids={"insight_1"},
    )

    assert context.target_sections == ["feature"]


def test_analyst_fallback_marks_uncovered_dimensions() -> None:
    analyst = AnalystOutput.build_fallback(
        focus_dimensions=["feature", "pricing"],
        evidence_briefs=[
            {
                "evidence_id": "ev_001",
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote_preview": "Cursor pricing starts at a public monthly plan.",
                "source_title": "Cursor Pricing",
                "source_url": "https://cursor.com/pricing",
            }
        ],
    )

    assert analyst.recommended_sections == ["pricing"]
    assert analyst.risk_flags == ["analyst_fallback_mode", "uncovered_dimension:feature"]


def test_analyst_output_slugifies_dimension_before_allowed_membership() -> None:
    output = AnalystOutput.parse_llm_content(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "User Feedback",
                    "finding": "Users report onboarding friction.",
                    "evidence_ids": ["ev_001"],
                    "confidence": "medium",
                }
            ],
        },
        allowed_evidence_ids={"ev_001"},
        allowed_dimensions={"user_feedback"},
    )

    assert output.insights[0].dimension == "user_feedback"


def test_analyst_output_filters_structured_comparisons() -> None:
    output = AnalystOutput.parse_llm_content(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "Feature",
                    "finding": "Cursor and Windsurf differ on repository context.",
                    "evidence_ids": ["ev_cursor"],
                    "confidence": "medium",
                }
            ],
            "comparisons": [
                {
                    "dimension": "Feature",
                    "cells": [
                        {
                            "competitor_id": "Cursor ",
                            "stance": "leader",
                            "summary": "Cursor has stronger repo context.",
                            "evidence_ids": ["ev_cursor", "ev_unknown"],
                        },
                        {
                            "competitor_id": "Windsurf",
                            "stance": "not_valid",
                            "summary": "Windsurf is competitive but less grounded here.",
                            "evidence_ids": ["ev_windsurf"],
                        },
                        {
                            "competitor_id": "UnknownCompetitor",
                            "stance": "leader",
                            "summary": "Should be filtered.",
                            "evidence_ids": ["ev_unknown"],
                        },
                    ],
                },
                {
                    "dimension": "Pricing",
                    "cells": [
                        {
                            "competitor_id": "Cursor",
                            "stance": "leader",
                            "summary": "Single-cell comparisons are not useful.",
                            "evidence_ids": ["ev_cursor"],
                        }
                    ],
                },
            ],
        },
        allowed_evidence_ids={"ev_cursor", "ev_windsurf"},
        allowed_dimensions={"feature", "pricing"},
        competitors={"Cursor", "Windsurf"},
    )

    assert len(output.comparisons) == 1
    comparison = output.comparisons[0]
    assert comparison.dimension == "feature"
    assert [cell.competitor_id for cell in comparison.cells] == ["Cursor", "Windsurf"]
    assert comparison.cells[0].evidence_ids == ["ev_cursor"]
    assert comparison.cells[1].stance == "unknown"


def test_analyst_output_downgrades_qualified_comparison_without_evidence() -> None:
    output = AnalystOutput.parse_llm_content(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "Feature",
                    "finding": "Cursor and Windsurf differ on repository context.",
                    "evidence_ids": ["ev_cursor"],
                    "confidence": "medium",
                }
            ],
            "comparisons": [
                {
                    "dimension": "Feature",
                    "cells": [
                        {
                            "competitor_id": "Cursor",
                            "stance": "leader",
                            "summary": "Cursor supposedly leads, but the evidence was filtered.",
                            "evidence_ids": ["ev_missing"],
                        },
                        {
                            "competitor_id": "Windsurf",
                            "stance": "competitive",
                            "summary": "Windsurf has grounded competing evidence.",
                            "evidence_ids": ["ev_windsurf"],
                        },
                    ],
                }
            ],
        },
        allowed_evidence_ids={"ev_cursor", "ev_windsurf"},
        allowed_dimensions={"feature"},
        competitors={"Cursor", "Windsurf"},
    )

    cells = output.comparisons[0].cells
    assert cells[0].competitor_id == "Cursor"
    assert cells[0].stance == "unknown"
    assert cells[0].evidence_ids == []
    assert cells[1].stance == "competitive"


def test_analyst_output_parses_structured_knowledge_with_server_ids() -> None:
    output = AnalystOutput.parse_llm_content(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "Feature",
                    "finding": "Cursor has repo-aware coding support.",
                    "evidence_ids": ["ev_feature"],
                    "confidence": "high",
                }
            ],
            "features": [
                {
                    "id": "llm_parent",
                    "competitor_id": "Cursor",
                    "name": "Repository context",
                    "description": "Understands broader repository context.",
                    "maturity": "advanced",
                    "evidence_ids": ["ev_feature"],
                },
                {
                    "id": "llm_child",
                    "competitor_id": "Cursor",
                    "name": "Codebase Q&A",
                    "parent_id": "llm_parent",
                    "maturity": "basic",
                    "evidence_ids": ["ev_feature"],
                },
            ],
            "pricings": [
                {
                    "id": "llm_price",
                    "competitor_id": "Cursor",
                    "model": "unknown",
                    "tiers": [{"name": "Team"}],
                    "free_plan": None,
                    "enterprise_plan": True,
                    "evidence_ids": ["ev_pricing"],
                }
            ],
            "personas": [
                {
                    "id": "llm_persona",
                    "name": "Engineering manager",
                    "role": "engineering_manager",
                    "pain_points": ["Code review load"],
                    "jobs_to_be_done": ["Improve delivery throughput"],
                    "evidence_ids": ["ev_feedback"],
                }
            ],
            "coverage": {
                "Cursor": {
                    "feature": "partial",
                    "pricing": "complete",
                    "feedback": "partial",
                }
            },
        },
        allowed_evidence_ids={"ev_feature", "ev_pricing", "ev_feedback"},
        allowed_dimensions={"feature"},
        competitors={"Cursor"},
    )

    assert [feature.id.startswith("feat_") for feature in output.features] == [True, True]
    assert output.features[1].parent_id == output.features[0].id
    assert output.pricings[0].id.startswith("price_")
    assert output.pricings[0].model == "unknown"
    assert output.personas[0].id.startswith("persona_")
    assert output.coverage["Cursor"]["pricing"] == "complete"


def test_analyst_output_filters_invalid_structured_knowledge() -> None:
    output = AnalystOutput.parse_llm_content(
        {
            "summary": "Summary with enough analyst context.",
            "insights": [
                {
                    "dimension": "Pricing",
                    "finding": "Cursor pricing evidence is available.",
                    "evidence_ids": ["ev_pricing"],
                    "confidence": "medium",
                }
            ],
            "features": [
                {
                    "competitor_id": "Cursor",
                    "name": "No grounding",
                    "evidence_ids": ["ev_missing"],
                },
                {
                    "competitor_id": "Unknown",
                    "name": "Wrong competitor",
                    "evidence_ids": ["ev_feature"],
                },
            ],
            "pricings": [
                {
                    "competitor_id": "Cursor",
                    "model": "seat",
                    "evidence_ids": ["ev_missing"],
                }
            ],
            "personas": [
                {
                    "name": "Buyer",
                    "role": "sales_leader",
                    "evidence_ids": ["ev_missing"],
                },
                {
                    "name": "Missing role",
                    "evidence_ids": ["ev_feedback"],
                },
            ],
            "coverage": {
                "Cursor": {"feature": "insufficient_data", "pricing": "made_up"},
                "Unknown": {"feature": "complete"},
            },
        },
        allowed_evidence_ids={"ev_feature", "ev_pricing", "ev_feedback"},
        allowed_dimensions={"pricing"},
        competitors={"Cursor"},
    )

    assert output.features == []
    assert output.pricings == []
    assert len(output.personas) == 1
    assert output.personas[0].evidence_ids == []
    assert output.coverage == {"Cursor": {"feature": "insufficient_data"}}


def test_analyst_fallback_marks_structured_knowledge_insufficient() -> None:
    analyst = AnalystOutput.build_fallback(
        focus_dimensions=["feature", "pricing"],
        competitors=["Cursor", "Windsurf"],
        evidence_briefs=[],
    )

    assert analyst.features == []
    assert analyst.pricings == []
    assert analyst.personas == []
    assert analyst.coverage == {
        "Cursor": {
            "feature": "insufficient_data",
            "pricing": "insufficient_data",
            "feedback": "insufficient_data",
        },
        "Windsurf": {
            "feature": "insufficient_data",
            "pricing": "insufficient_data",
            "feedback": "insufficient_data",
        },
    }


def test_analyst_output_skips_out_of_focus_insight_and_audits_reason() -> None:
    dropped: dict[str, int] = {}

    with pytest.raises(ValidationError):
        AnalystOutput.parse_llm_content(
            {
                "summary": "Summary with enough analyst context.",
                "insights": [
                    {
                        "dimension": "User Feedback",
                        "finding": "Users report onboarding friction.",
                        "evidence_ids": ["ev_001"],
                        "confidence": "medium",
                    }
                ],
            },
            allowed_evidence_ids={"ev_001"},
            allowed_dimensions={"pricing"},
            dropped_dimensions=dropped,
        )

    assert dropped == {"out_of_focus": 1}


def test_writer_report_output_marks_uncovered_target_sections() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["feature", "pricing"],
        allowed_evidence_ids=frozenset({"ev_001"}),
        allowed_insight_ids=frozenset(),
    )
    output = WriterReportOutput.parse_llm_content(
        {
            "template_id": "battlecard_default",
            "title": "Battlecard",
            "executive_summary": "Executive summary grounded in collected evidence.",
            "sections": [
                {
                    "section_id": "feature",
                    "title": "Feature",
                    "content_markdown": (
                        "Feature comparison with enough detail to satisfy writer schema validation."
                    ),
                    "evidence_refs": ["ev_001"],
                    "insight_refs": [],
                }
            ],
            "risk_callouts": [],
        },
        execution_context=context,
    )

    assert [section.section_id for section in output.sections] == ["feature"]
    assert output.risk_callouts == ["uncovered_section:pricing"]


def test_intake_turn_output_requires_clarify_for_ask() -> None:
    with pytest.raises(ValidationError):
        IntakeTurnOutput.model_validate(
            {
                "action": "ask",
                "draft_patch": {},
                "clarify_request": None,
                "reasoning_summary": "",
            }
        )


def test_planner_output_parses_research_tasks() -> None:
    draft = RunIntakeDraft(user_query="compare AI coding tools", competitors_explicit=["Cursor"])
    output = PlannerOutput.parse_llm_content(
        {
            "rationale": "Research explicit competitors first.",
            "tasks": [
                {
                    "stage": "research",
                    "title": "Research Cursor",
                    "description": "Collect evidence",
                    "competitor_id": "Cursor",
                    "focus_dimensions": ["feature"],
                }
            ],
        },
        draft=draft,
    )
    tasks = output.to_plan_tasks()
    assert len(tasks) == 1
    assert tasks[0].competitor_id == "Cursor"


def test_planner_output_normalizes_or_falls_back_non_contract_dimensions() -> None:
    draft = RunIntakeDraft(
        user_query="对比 AI 编程工具",
        competitors_explicit=["Cursor"],
        focus_dimensions=["产品定位", "pricing_strategy"],
    )
    output = PlannerOutput.parse_llm_content(
        {
            "rationale": "Research explicit competitors first.",
            "tasks": [
                {
                    "stage": "research",
                    "title": "Research Cursor",
                    "description": "Collect evidence",
                    "competitor_id": "Cursor",
                    "focus_dimensions": ["产品定位", "enterprise capabilities"],
                }
            ],
        },
        draft=draft,
    )

    task = output.to_plan_tasks()[0]
    assert task.focus_dimensions == ["enterprise_capabilities"]


def test_dimension_aliases_share_canonical_namespace() -> None:
    assert validate_dimension("china_vs_global") == "market_differences"
    assert validate_dimension("china_vs_global_market_dynamics") == "market_differences"
    assert validate_dimension("enterprise_features") == "enterprise_capabilities"
    assert validate_dimension("enterprise_capabilities_assessme") == "enterprise_capabilities"
    assert validate_dimension("product_positioning_analysis") == "product_positioning"
    assert validate_dimension("pricing_strategy_comparison") == "pricing_strategy"
    assert validate_dimension("investment_recommendation") == "strategic_recommendations"
    assert validate_dimension("strategic_investment_recommendat") == "strategic_recommendations"


def test_supervisor_tool_call_output_validates_batch_topics() -> None:
    with pytest.raises(ValueError):
        SupervisorToolCallOutput.parse_llm_content(
            {
                "chosen_tool": "ConductResearchBatch",
                "tool_args": {
                    "topics": [
                        {
                            "research_topic": "t1",
                            "competitor_id": "A",
                            "focus_dimensions": ["feature"],
                            "max_iterations": 3,
                            "fallback_to_offline": True,
                        },
                        {
                            "research_topic": "t2",
                            "competitor_id": "A",
                            "focus_dimensions": ["feature"],
                            "max_iterations": 3,
                            "fallback_to_offline": True,
                        },
                    ],
                    "parallelism_rationale": "dup",
                },
                "reasoning_summary": "batch",
            }
        )


def test_discovery_extract_output_dedupes_competitors() -> None:
    output = DiscoveryExtractOutput.parse_llm_content(
        {"competitors": ["Cursor", "Cursor", "Windsurf"]}
    )
    assert output.competitors == ["Cursor", "Windsurf"]


def test_discovery_extract_output_parses_grounded_candidates() -> None:
    output = DiscoveryExtractOutput.parse_llm_content(
        {
            "candidates": [
                {
                    "name": "Cursor",
                    "is_competitor": True,
                    "relevance_reason": "AI coding product in the target market.",
                    "evidence_quote": "Cursor is an AI code editor.",
                },
                {
                    "name": "TechCrunch",
                    "is_competitor": False,
                    "relevance_reason": "Publisher, not a product competitor.",
                    "evidence_quote": "TechCrunch reported on AI coding tools.",
                },
            ]
        }
    )

    assert output.competitors == ["Cursor"]
    assert output.candidates[0].evidence_quote == "Cursor is an AI code editor."
    assert output.candidates[1].is_competitor is False


def test_researcher_decision_to_action_tuple_search_web() -> None:
    decision = ResearcherDecisionOutput.parse_llm_content(
        {
            "action": "search_web",
            "action_args": {"query": "Cursor pricing", "dimension": "pricing"},
            "reasoning_summary": "Need pricing evidence",
        }
    )
    action_tuple = decision.to_action_tuple(competitor_id="Cursor")
    assert action_tuple is not None
    action, args = action_tuple
    assert action == "search_web"
    assert args["query"] == "Cursor pricing"


def test_researcher_decision_dimension_falls_back_to_pending_when_out_of_focus() -> None:
    decision = ResearcherDecisionOutput.parse_llm_content(
        {
            "action": "search_web",
            "action_args": {
                "query": "Cursor product positioning pricing strategy",
                "dimension": "product_positioning_pricing_strategy",
            },
            "reasoning_summary": "Need pricing evidence",
        }
    )

    action_tuple = decision.to_action_tuple(
        competitor_id="Cursor",
        focus_dimensions=["pricing"],
        pending_dimensions=["pricing"],
    )

    assert action_tuple is not None
    action, args = action_tuple
    assert action == "search_web"
    assert args["dimension"] == "pricing"


def test_researcher_decision_fetch_url_without_dimension_does_not_use_next_pending() -> None:
    decision = ResearcherDecisionOutput.parse_llm_content(
        {
            "action": "fetch_url",
            "action_args": {"url": "https://cursor.com/pricing"},
            "reasoning_summary": "Follow a pricing result URL",
        }
    )

    action_tuple = decision.to_action_tuple(
        competitor_id="Cursor",
        focus_dimensions=["pricing", "security"],
        pending_dimensions=["security"],
    )

    assert action_tuple is not None
    action, args = action_tuple
    assert action == "fetch_url"
    assert "dimension" not in args


def test_researcher_decision_extract_structured_without_dimension_does_not_use_next_pending() -> None:
    decision = ResearcherDecisionOutput.parse_llm_content(
        {
            "action": "extract_structured",
            "action_args": {"text": "Cursor pricing includes public team plan evidence."},
            "reasoning_summary": "Extract details from the last fetched page",
        }
    )

    action_tuple = decision.to_action_tuple(
        competitor_id="Cursor",
        focus_dimensions=["pricing", "security"],
        pending_dimensions=["security"],
    )

    assert action_tuple is not None
    action, args = action_tuple
    assert action == "extract_structured"
    assert "dimension" not in args


def test_qa_semantic_output_normalizes_dict() -> None:
    output = QASemanticOutput.parse_llm_content(
        {
            "semantic_audit_passed": False,
            "reject_to": "writer",
            "severity": "blocking",
            "finding": "Missing pricing evidence",
            "required_fields": ["reports.content_json.sections"],
            "unsupported_numeric_claims": [
                {
                    "claim": "效率提升 28%",
                    "section_id": "efficiency",
                    "reason": "Cited evidence does not mention 28%.",
                },
                {
                    "claim": "",
                    "section_id": "pricing",
                    "reason": "invalid item is filtered",
                },
            ],
            "dimension_results": {
                "depth": False,
                "citation_coverage": False,
                "faithfulness": True,
                "instruction_following": True,
            },
        }
    )
    normalized = output.to_normalized_dict()
    assert normalized["reject_to"] == "writer"
    assert normalized["semantic_audit_passed"] is False
    assert normalized["unsupported_numeric_claims"] == [
        {
            "claim": "效率提升 28%",
            "section_id": "efficiency",
            "reason": "Cited evidence does not mention 28%.",
        }
    ]
    assert normalized["dimension_results"] == {
        "depth": False,
        "citation_coverage": False,
        "faithfulness": True,
        "instruction_following": True,
    }
