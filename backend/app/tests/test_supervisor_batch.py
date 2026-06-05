from __future__ import annotations

from agents.nodes.supervisor import _decision_from_tool_output, _fallback_decision
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
    decision = _fallback_decision(
        run_id="run_test",
        iteration=2,
        competitors=["comp_cursor", "comp_windsurf", "comp_copilot"],
        researched_competitors=["comp_cursor"],
        analysis_done=False,
        report_draft_done=False,
        triggered_by="researcher_completion",
        user_query="compare coding assistants",
    )

    assert decision.chosen_tool == "ConductResearchBatch"
    topics = decision.tool_args["topics"]
    assert isinstance(topics, list)
    assert len(topics) == 2
    assert {item["competitor_id"] for item in topics} == {"comp_windsurf", "comp_copilot"}
