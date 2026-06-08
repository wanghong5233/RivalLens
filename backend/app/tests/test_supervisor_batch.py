from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.state import ACCUMULATING_STATE_FIELDS, spread_without_accumulators
from agents.nodes.supervisor import (
    _decision_from_qa_feedback,
    _decision_from_tool_output,
    _derive_write_sections,
    _fallback_decision,
    _discovery_search_queries,
    _resolve_fallback_dimensions,
    supervisor_node,
)
from schemas.intake import RunIntakeDraft
from schemas.agent_outputs import SupervisorToolCallOutput
from service.event_bus import RunEventType
from service.llm.response import LLMResponse


def _fake_supervisor_llm_response() -> LLMResponse:
    return LLMResponse(
        model_slot="research",
        provider="fake",
        model_name="fake-supervisor-model",
        prompt_preview="fake supervisor prompt",
        prompt_hash="fake_hash",
        content={},
        prompt_tokens=1,
        completion_tokens=1,
        latency_ms=1,
        error=None,
    )


def test_spread_without_accumulators_drops_all_operator_add_fields() -> None:
    state = {
        "run_id": "run_test",
        "competitors": ["Cursor"],
        "discovered_competitors": ["Windsurf"],
        "researched_competitors": ["Cursor"],
        "follow_up_queue": [{"id": "fu_1"}],
        "status": "running",
    }

    result = spread_without_accumulators(state)

    for field_name in ACCUMULATING_STATE_FIELDS:
        assert field_name not in result
    assert result == {"run_id": "run_test", "status": "running"}


async def _run_supervisor_node_with_output(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output: SupervisorToolCallOutput,
    state: dict[str, object],
    step_id: str,
) -> tuple[dict[str, object], list[tuple[RunEventType, str | None, dict[str, object]]]]:
    captured: list[tuple[RunEventType, str | None, dict[str, object]]] = []

    async def _fake_complete_structured(**_: object) -> SimpleNamespace:
        return SimpleNamespace(
            value=output,
            llm_response=_fake_supervisor_llm_response(),
        )

    async def _fake_persist_iteration(**_: object) -> str:
        return step_id

    async def _fake_load_pending_follow_ups(**_: object) -> list[dict[str, object]]:
        return []

    async def _fake_emit_run_event(
        *,
        run_id: str,
        event_type: RunEventType,
        step_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        del run_id
        captured.append((event_type, step_id, dict(payload or {})))

    monkeypatch.setattr("agents.nodes.supervisor.complete_structured", _fake_complete_structured)
    monkeypatch.setattr("agents.nodes.supervisor._persist_iteration", _fake_persist_iteration)
    monkeypatch.setattr(
        "agents.nodes.supervisor._load_pending_follow_ups",
        _fake_load_pending_follow_ups,
    )
    monkeypatch.setattr("agents.nodes.supervisor.emit_run_event", _fake_emit_run_event)
    monkeypatch.setattr("agents.nodes.supervisor.get_session_factory", lambda: object())

    new_state = await supervisor_node(state)
    return dict(new_state), captured


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


def test_discovery_search_queries_localize_chinese_market_scope() -> None:
    queries = _discovery_search_queries(
        user_query="OPC 变现工具",
        market_scope="中国市场",
        response_language="zh",
    )

    assert queries
    assert all("中国市场" in query for query in queries)
    assert any("竞品" in query or "替代" in query for query in queries)
    assert not any("competitors alternatives" in query for query in queries)


def test_fallback_decision_uses_localized_discovery_queries() -> None:
    decision = _fallback_decision(
        run_id="run_test",
        iteration=1,
        competitors=[],
        researched_competitors=[],
        analysis_done=False,
        report_draft_done=False,
        triggered_by="user_query",
        user_query="OPC 变现工具",
        fallback_dimensions=["feature", "pricing"],
        fallback_sections=["feature", "pricing"],
        market_scope="中国市场",
        response_language="zh",
    )

    assert decision.chosen_tool == "DiscoverCompetitors"
    search_queries = decision.tool_args["search_queries"]
    assert isinstance(search_queries, list)
    assert all("中国市场" in query for query in search_queries)
    assert not any("competitors alternatives" in query for query in search_queries)


@pytest.mark.asyncio
async def test_supervisor_node_marks_llm_tool_output_for_happy_path_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SupervisorToolCallOutput.parse_llm_content(
        {
            "chosen_tool": "ConductResearchBatch",
            "tool_args": {
                "topics": [
                    {
                        "research_topic": "comp_cursor vs user_query=fake",
                        "competitor_id": "comp_cursor",
                        "focus_dimensions": ["feature", "pricing"],
                        "max_iterations": 6,
                        "fallback_to_offline": True,
                    }
                ],
                "parallelism_rationale": "parallelize independent competitors",
            },
            "reasoning_summary": "Batch pending competitors.",
        }
    )
    new_state, captured = await _run_supervisor_node_with_output(
        monkeypatch,
        output=output,
        step_id="step_supervisor_dimension",
        state={
            "run_id": "run_test",
            "user_query": "compare coding assistants",
            "competitors": ["comp_cursor"],
            "researched_competitors": [],
            "analysis_done": False,
            "report_draft_done": False,
            "current_iteration": 0,
            "decisions": [],
        },
    )

    assert new_state["next_action"] == "researcher"
    for field_name in ACCUMULATING_STATE_FIELDS:
        assert field_name not in new_state
    assert captured == [
        (
            RunEventType.SUPERVISOR_DECISION,
            "step_supervisor_dimension",
            {
                "iteration": 1,
                "chosen_tool": "ConductResearchBatch",
                "triggered_by": "user_query",
                "outcome": "dispatched",
                "plan_task_ids": [],
                "consumed_follow_up_ids": [],
                "dimension_source": "llm_tool_output",
            },
        )
    ]


@pytest.mark.asyncio
async def test_supervisor_node_leaves_dimension_source_empty_for_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SupervisorToolCallOutput.parse_llm_content(
        {
            "chosen_tool": "DiscoverCompetitors",
            "tool_args": {
                "search_queries": ["coding assistant alternatives"],
                "domain_context": "AI coding assistant",
                "max_results": 5,
            },
            "reasoning_summary": "Discover competitors first.",
        }
    )
    _, captured = await _run_supervisor_node_with_output(
        monkeypatch,
        output=output,
        step_id="step_supervisor_discover",
        state={
            "run_id": "run_test",
            "user_query": "find competitors",
            "competitors": [],
            "researched_competitors": [],
            "analysis_done": False,
            "report_draft_done": False,
            "current_iteration": 0,
            "decisions": [],
        },
    )

    assert captured[0][2]["chosen_tool"] == "DiscoverCompetitors"
    assert captured[0][2]["dimension_source"] is None


@pytest.mark.asyncio
async def test_supervisor_finalize_degrades_when_researcher_had_zero_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = SupervisorToolCallOutput.parse_llm_content(
        {
            "chosen_tool": "Finalize",
            "tool_args": {
                "completion_reason": "all_dimensions_covered",
                "notes": "Done",
            },
            "reasoning_summary": "Workflow completed with a degraded researcher step.",
        }
    )
    new_state, _ = await _run_supervisor_node_with_output(
        monkeypatch,
        output=output,
        step_id="step_supervisor_degraded_research",
        state={
            "run_id": "run_test",
            "user_query": "compare coding assistants",
            "competitors": ["comp_cursor"],
            "researched_competitors": ["comp_cursor"],
            "researcher_degraded_competitors": ["comp_cursor"],
            "analysis_done": True,
            "report_draft_done": True,
            "current_iteration": 0,
            "decisions": [],
        },
    )

    assert new_state["status"] == "degraded"


@pytest.mark.asyncio
async def test_qa_writer_rewrite_reuses_prior_writer_contract() -> None:
    prior_writer_step = SimpleNamespace(
        run_id="run_test",
        agent_name="writer",
        payload={
            "template_id": "executive_briefing",
            "target_sections": ["product_positioning", "pricing_strategy"],
        },
    )

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, *_: object) -> object:
            return prior_writer_step

    decision_bundle = await _decision_from_qa_feedback(
        session_factory=lambda: _FakeSession(),  # type: ignore[arg-type]
        run_id="run_test",
        iteration=3,
        triggered_by="qa_rejection",
        qa_outcome="rejected",
        qa_reject_to="writer",
        qa_reasons=["Unsupported numeric claims."],
        qa_unsupported_numeric_claims=[{"claim": "$40/seat"}],
        user_query="compare coding assistants",
        competitors=["Cursor"],
        fallback_dimensions=["feature"],
        fallback_sections=["feature", "differentiation"],
        pending_review_target_step_id="step_writer_v1",
    )

    assert decision_bundle is not None
    decision, _, forced_degraded = decision_bundle
    assert forced_degraded is False
    assert decision.chosen_tool == "Write"
    assert decision.tool_args["template_id"] == "executive_briefing"
    assert decision.tool_args["sections"] == ["product_positioning", "pricing_strategy"]
    assert decision.tool_args["unsupported_numeric_claims"] == [{"claim": "$40/seat"}]


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
