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


def test_writer_report_output_requires_target_sections() -> None:
    context = WriterExecutionContext(
        template_id="battlecard_default",
        target_sections=["feature", "pricing"],
        allowed_evidence_ids=frozenset({"ev_001"}),
        allowed_insight_ids=frozenset(),
    )
    with pytest.raises(ValidationError):
        WriterReportOutput.parse_llm_content(
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


def test_qa_semantic_output_normalizes_dict() -> None:
    output = QASemanticOutput.parse_llm_content(
        {
            "semantic_audit_passed": False,
            "reject_to": "writer",
            "severity": "blocking",
            "finding": "Missing pricing evidence",
            "required_fields": ["reports.content_json.sections"],
        }
    )
    normalized = output.to_normalized_dict()
    assert normalized["reject_to"] == "writer"
    assert normalized["semantic_audit_passed"] is False
