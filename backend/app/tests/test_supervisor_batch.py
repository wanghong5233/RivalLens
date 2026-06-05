from __future__ import annotations

from agents.nodes.supervisor import (
    _decision_from_tool_output,
    _derive_write_sections,
    _fallback_decision,
    _resolve_fallback_dimensions,
)
from schemas.intake import RunIntakeDraft
from schemas.agent_outputs import SupervisorToolCallOutput


def test_decision_from_tool_output_accepts_conduct_research_batch() -> None:
    output = SupervisorToolCallOutput.parse_llm_content(
        {
            "chosen_tool": "ConductResearchBatch",
            "tool_args": {
                "topics": [
                    {
                        "research_topic": "comp_cursor vs user_query=fake",
                        "competitor_id": "comp_cursor",
                        "focus_dimensions": ["feature", "pricing", "user_feedback"],
                        "max_iterations": 6,
                        "fallback_to_offline": True,
                    },
                    {
                        "research_topic": "comp_windsurf vs user_query=fake",
                        "competitor_id": "comp_windsurf",
                        "focus_dimensions": ["feature", "pricing", "user_feedback"],
                        "max_iterations": 6,
                        "fallback_to_offline": True,
                    },
                ],
                "parallelism_rationale": "parallelize independent competitors",
            },
            "reasoning_summary": "Batch pending competitors.",
        }
    )

    decision = _decision_from_tool_output(
        run_id="run_test",
        iteration=1,
        output=output,
        triggered_by="user_query",
    )

    assert decision.chosen_tool == "ConductResearchBatch"
    topics = decision.tool_args["topics"]
    assert isinstance(topics, list)
    assert len(topics) == 2
    assert {item["competitor_id"] for item in topics} == {"comp_cursor", "comp_windsurf"}
    assert decision.outcome == "dispatched"


def test_decision_from_tool_output_truncates_batch_topics_to_max_eight() -> None:
    output = SupervisorToolCallOutput.parse_llm_content(
        {
            "chosen_tool": "ConductResearchBatch",
            "tool_args": {
                "topics": [
                    {
                        "research_topic": f"comp_{idx} vs user_query=fake",
                        "competitor_id": f"comp_{idx}",
                        "focus_dimensions": ["feature", "pricing", "user_feedback"],
                        "max_iterations": 6,
                        "fallback_to_offline": True,
                    }
                    for idx in range(10)
                ],
                "parallelism_rationale": "parallelize independent competitors",
            },
            "reasoning_summary": "Batch pending competitors.",
        }
    )
    decision = _decision_from_tool_output(
        run_id="run_test",
        iteration=1,
        output=output,
        triggered_by="user_query",
    )

    topics = decision.tool_args["topics"]
    assert isinstance(topics, list)
    assert len(topics) == 8
    assert topics[0]["competitor_id"] == "comp_0"
    assert topics[-1]["competitor_id"] == "comp_7"


def test_fallback_decision_prefers_batch_when_multiple_competitors_pending() -> None:
    fallback_dimensions = ["feature", "pricing", "user_feedback"]
    decision = _fallback_decision(
        run_id="run_test",
        iteration=2,
        competitors=["comp_cursor", "comp_windsurf", "comp_copilot"],
        researched_competitors=["comp_cursor"],
        analysis_done=False,
        report_draft_done=False,
        triggered_by="researcher_completion",
        user_query="compare coding assistants",
        fallback_dimensions=fallback_dimensions,
        fallback_sections=_derive_write_sections(focus_dimensions=fallback_dimensions),
    )

    assert decision.chosen_tool == "ConductResearchBatch"
    topics = decision.tool_args["topics"]
    assert isinstance(topics, list)
    assert len(topics) == 2
    assert {item["competitor_id"] for item in topics} == {"comp_windsurf", "comp_copilot"}


def test_resolve_fallback_dimensions_prefers_matching_plan_task_over_hints() -> None:
    dimensions, source = _resolve_fallback_dimensions(
        plan_tree={
            "tasks": [
                {
                    "stage": "research",
                    "competitor_id": "comp_windsurf",
                    "focus_dimensions": ["supply_chain", "implementation"],
                    "enabled": True,
                }
            ]
        },
        intake_draft={"focus_dimensions": ["pricing"]},
        user_query="compare pricing for coding assistants",
        competitors=["comp_cursor", "comp_windsurf"],
        researched_competitors=["comp_cursor"],
        analysis_done=False,
        report_draft_done=False,
    )

    assert source == "upstream_task"
    assert dimensions == ["supply_chain", "implementation"]


def test_resolve_fallback_dimensions_uses_intake_before_hints() -> None:
    dimensions, source = _resolve_fallback_dimensions(
        plan_tree=None,
        intake_draft=RunIntakeDraft(
            user_query="分析 ERP 实施风险和供应链集成差异",
            focus_dimensions=["implementation", "integration"],
        ),
        user_query="compare pricing for supply chain ERP",
        competitors=["comp_a", "comp_b"],
        researched_competitors=[],
        analysis_done=False,
        report_draft_done=False,
    )

    assert source == "intake"
    assert dimensions == ["implementation", "integration"]


def test_resolve_fallback_dimensions_uses_hints_only_without_upstream() -> None:
    dimensions, source = _resolve_fallback_dimensions(
        plan_tree=None,
        intake_draft=None,
        user_query="我想比较这些产品的定价和企业套餐",
        competitors=["comp_a", "comp_b"],
        researched_competitors=[],
        analysis_done=False,
        report_draft_done=False,
    )

    assert source == "hints"
    assert dimensions[0] == "pricing"


def test_resolve_fallback_dimensions_defaults_without_upstream_or_hints() -> None:
    dimensions, source = _resolve_fallback_dimensions(
        plan_tree=None,
        intake_draft=None,
        user_query="compare these products",
        competitors=["comp_a", "comp_b"],
        researched_competitors=[],
        analysis_done=False,
        report_draft_done=False,
    )

    assert source == "default"
    assert dimensions == ["feature", "pricing", "user_feedback"]
