from __future__ import annotations

from agents.nodes.supervisor import _fallback_decision, _try_llm_decision
from service.llm.response import LLMResponse


def _build_supervisor_llm_response(content: dict[str, object]) -> LLMResponse:
    return LLMResponse(
        model_slot="research",
        provider="fake_llm",
        model_name="fake-research-model",
        prompt_preview="fake prompt",
        prompt_hash="fake_hash",
        content=content,
        prompt_tokens=10,
        completion_tokens=20,
        latency_ms=10,
        error=None,
    )


def test_try_llm_decision_accepts_conduct_research_batch() -> None:
    llm_response = _build_supervisor_llm_response(
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

    decision = _try_llm_decision(
        run_id="run_test",
        iteration=1,
        llm_response=llm_response,
        triggered_by="user_query",
    )

    assert decision is not None
    assert decision.chosen_tool == "ConductResearchBatch"
    topics = decision.tool_args["topics"]
    assert isinstance(topics, list)
    assert len(topics) == 2
    assert {item["competitor_id"] for item in topics} == {"comp_cursor", "comp_windsurf"}
    assert decision.outcome == "dispatched"


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
