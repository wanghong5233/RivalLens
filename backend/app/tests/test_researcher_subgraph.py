from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.subgraphs.researcher import (
    COMPRESS_AFTER_TURNS,
    ResearcherSubState,
    _build_coverage_matrix,
    _fallback_action,
    _fallback_fetch_url,
    _fallback_query_variants,
    _is_official_priority_dimension,
    _ordered_source_types_for_dimension,
    _pending_dimensions_from_coverage,
    _pick_url_for_dimension,
    get_researcher_subgraph,
)
from service.collector.base import CollectorObservation, CollectorSnippet, ToolObservationResult
from service.llm.response import LLMResponse


@dataclass
class _FakeSequentialLLMClient:
    responses_by_slot: dict[str, list[LLMResponse]]

    async def complete_json(
        self,
        *,
        model_slot: str = "research",
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        prompt: str | None = None,
        fallback_system_prompt: str | None = None,
        fallback_user_prompt: str | None = None,
    ) -> LLMResponse:
        del system_prompt, user_prompt, prompt, fallback_system_prompt, fallback_user_prompt
        queue = self.responses_by_slot.get(model_slot, [])
        if queue:
            return queue.pop(0)
        return LLMResponse(
            model_slot=model_slot,
            provider="fake_llm",
            model_name=f"fake-{model_slot}",
            prompt_preview="fallback",
            prompt_hash=f"fallback-{model_slot}",
            content={},
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            error=None,
        )


def test_is_official_priority_dimension_matches_buyer_critical() -> None:
    assert _is_official_priority_dimension("pricing_strategy") is True
    assert _is_official_priority_dimension("enterprise_capabilities") is True
    assert _is_official_priority_dimension("security_compliance") is True
    assert _is_official_priority_dimension("product_positioning") is False


def test_pick_url_for_dimension_prefers_official_host_for_pricing() -> None:
    urls = [
        "https://www.g2.com/products/cursor/pricing",
        "https://cursor.com/pricing",
    ]
    # cursor.com is in the curated official host map; it must win for pricing.
    selected = _pick_url_for_dimension(
        urls, "pricing_strategy", official_hosts={"cursor.com", "www.cursor.com"}
    )
    assert selected == "https://cursor.com/pricing"


def test_fallback_action_targets_official_domain_for_pricing() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "research_topic": "cursor pricing",
        "competitor_id": "cursor",
        "pending_dimensions": ["pricing_strategy"],
        "resolved_official_urls": ["https://cursor.com/pricing"],
        "resolved_official_hosts": ["cursor.com"],
        "resolved_source_pages": [
            {
                "url": "https://cursor.com/pricing",
                "source_type": "pricing_page",
            }
        ],
        "observations_log": [],
    }
    action, args = _fallback_action(state)
    assert action == "fetch_url"
    assert args["url"] == "https://cursor.com/pricing"


def test_fallback_fetch_url_prefers_docs_for_feature_dimensions() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "competitor_id": "cursor",
        "resolved_official_hosts": ["cursor.com"],
        "resolved_source_pages": [
            {"url": "https://cursor.com/pricing", "source_type": "pricing_page"},
            {"url": "https://cursor.com/docs", "source_type": "docs"},
        ],
        "resolved_official_urls": ["https://cursor.com/"],
        "reference_urls": [],
        "discovered_urls": [],
    }

    selected = _fallback_fetch_url(state=state, dimension="feature_comparison")
    assert selected == "https://cursor.com/docs"


def test_source_routing_prefers_public_review_for_user_feedback() -> None:
    ordered = _ordered_source_types_for_dimension("user_feedback")
    assert ordered[0] == "public_review"


def test_coverage_matrix_feedback_requires_public_review_source() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "focus_dimensions": ["user_feedback"],
        "resolved_official_hosts": ["cursor.com"],
    }
    article_only = _build_coverage_matrix(
        state=state,
        evidence_drafts=[
            {
                "dimension": "user_feedback",
                "source_type": "article",
                "source_url": "https://blog.example.com/review",
                "metadata": {},
            }
        ],
    )
    assert article_only["user_feedback"]["covered"] is False
    assert article_only["user_feedback"]["public_review_pass"] is False

    with_public_review = _build_coverage_matrix(
        state=state,
        evidence_drafts=[
            {
                "dimension": "user_feedback",
                "source_type": "public_review",
                "source_url": "https://www.g2.com/products/cursor/reviews",
                "metadata": {},
            }
        ],
    )
    assert with_public_review["user_feedback"]["covered"] is True
    assert with_public_review["user_feedback"]["public_review_pass"] is True


def test_coverage_matrix_requires_high_rerank_score_when_scored() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "focus_dimensions": ["pricing"],
        "resolved_official_hosts": ["cursor.com"],
    }
    low_score = _build_coverage_matrix(
        state=state,
        evidence_drafts=[
            {
                "dimension": "pricing",
                "source_type": "pricing_page",
                "source_url": "https://cursor.com/pricing",
                "metadata": {"rerank_score": 0.1},
            }
        ],
    )
    assert low_score["pricing"]["rerank_pass"] is False
    assert low_score["pricing"]["covered"] is False

    high_score = _build_coverage_matrix(
        state=state,
        evidence_drafts=[
            {
                "dimension": "pricing",
                "source_type": "pricing_page",
                "source_url": "https://cursor.com/pricing",
                "metadata": {"rerank_score": 0.8},
            },
            {
                "dimension": "pricing",
                "source_type": "official_site",
                "source_url": "https://cursor.com/enterprise",
                "metadata": {"rerank_score": 0.82},
            },
        ],
    )
    assert high_score["pricing"]["rerank_pass"] is True
    assert high_score["pricing"]["covered"] is True


def test_pending_dimensions_prioritize_least_attempted_dimension() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "focus_dimensions": ["feature", "pricing", "user_feedback"],
        "observations_log": [
            {"tool": "extract_structured", "args": {"dimension": "feature"}},
            {"tool": "extract_structured", "args": {"dimension": "pricing"}},
            {"tool": "extract_structured", "args": {"dimension": "pricing"}},
        ],
    }
    pending = _pending_dimensions_from_coverage(
        focus_dimensions=["feature", "pricing", "user_feedback"],
        coverage_matrix={
            "feature": {"covered": False},
            "pricing": {"covered": False},
            "user_feedback": {"covered": False},
        },
        state=state,
    )
    assert pending[0] == "user_feedback"


def test_pending_dimensions_exhausts_extract_only_loops() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "focus_dimensions": ["pricing"],
        "observations_log": [
            {"tool": "extract_structured", "args": {"dimension": "pricing"}},
        ],
    }
    pending = _pending_dimensions_from_coverage(
        focus_dimensions=["pricing"],
        coverage_matrix={"pricing": {"covered": False}},
        state=state,
    )
    assert pending == []


def test_pending_dimensions_keep_feedback_when_no_evidence_even_after_attempts() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "focus_dimensions": ["user_feedback"],
        "observations_log": [
            {"tool": "search_web", "args": {"dimension": "user_feedback"}},
            {"tool": "fetch_url", "args": {"dimension": "user_feedback"}},
            {"tool": "fetch_url", "args": {"dimension": "user_feedback"}},
        ],
    }
    pending = _pending_dimensions_from_coverage(
        focus_dimensions=["user_feedback"],
        coverage_matrix={
            "user_feedback": {"covered": False, "evidence_count": 0},
        },
        state=state,
    )
    assert pending == ["user_feedback"]


def test_pending_dimensions_exhaust_feedback_after_evidence_exists() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "focus_dimensions": ["user_feedback"],
        "observations_log": [
            {"tool": "search_web", "args": {"dimension": "user_feedback"}},
            {"tool": "fetch_url", "args": {"dimension": "user_feedback"}},
            {"tool": "fetch_url", "args": {"dimension": "user_feedback"}},
        ],
    }
    pending = _pending_dimensions_from_coverage(
        focus_dimensions=["user_feedback"],
        coverage_matrix={
            "user_feedback": {"covered": False, "evidence_count": 1},
        },
        state=state,
    )
    assert pending == []


def test_fallback_query_variants_adds_feedback_intent_query_for_zh() -> None:
    state: ResearcherSubState = {  # type: ignore[typeddict-item]
        "competitor_id": "Cursor",
        "response_language": "zh",
        "market_scope": "中国",
        "resolved_official_hosts": ["cursor.com"],
    }
    variants = _fallback_query_variants(
        state=state,
        dimension="user_feedback",
        primary_query="Cursor user_feedback AI coding",
        base_query="Cursor user_feedback",
    )
    assert variants
    assert "评价 口碑 优缺点 用户反馈" in variants[0]


def _llm_response(model_slot: str, content: dict[str, object]) -> LLMResponse:
    return LLMResponse(
        model_slot=model_slot,
        provider="fake_llm",
        model_name=f"fake-{model_slot}",
        prompt_preview="preview",
        prompt_hash=f"hash-{model_slot}-{len(str(content))}",
        content=content,
        prompt_tokens=1,
        completion_tokens=1,
        latency_ms=1,
        error=None,
    )


def _base_state() -> ResearcherSubState:
    return {
        "run_id": "run_test",
        "research_topic": "cursor pricing",
        "competitor_id": "comp_cursor",
        "focus_dimensions": ["pricing"],
        "pending_dimensions": ["pricing"],
        "queried_dimensions": [],
        "pending_action_args": {},
        "turn_count": 0,
        "max_turns": 6,
        "compression_count": 0,
        "last_compressed_turn": -1,
        "messages": [],
        "observations_log": [],
        "observation_briefs": [],
        "evidence_drafts": [],
        "llm_calls": [],
        "next_action": "tool_exec",
        "final_summary": "",
        "compressed_summary": "",
        "domain_hint": None,
        "reference_urls": [],
        "discovered_urls": [],
        "resolved_official_urls": [],
        "resolved_official_hosts": [],
        "resolved_source_pages": [],
        "search_call_count": 0,
        "official_fetch_count": 0,
        "coverage_matrix": {},
    }


@pytest.mark.asyncio
async def test_researcher_subgraph_collects_evidence_from_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_researcher_subgraph.cache_clear()
    fake_client = _FakeSequentialLLMClient(
        responses_by_slot={
            "research": [
                _llm_response(
                    "research",
                    {
                        "action": "extract_structured",
                        "action_args": {
                            "text": "Cursor starts at $20 per user/month.",
                            "source_url": "https://cursor.com/pricing",
                            "source_title": "Cursor Pricing",
                            "dimension": "pricing",
                            "competitor_id": "comp_cursor",
                        },
                        "reasoning_summary": "collect pricing evidence",
                    },
                ),
                _llm_response(
                    "research",
                    {
                        "action": "finalize",
                        "action_args": {"summary": "done"},
                        "reasoning_summary": "enough",
                    },
                ),
            ]
        }
    )
    monkeypatch.setattr("service.llm.harness.get_llm_client", lambda: fake_client)

    known_quotes = {"Cursor starts at $20 per user/month."}

    class _FakeRegistry:
        async def invoke(self, action: str, *, args: dict[str, object]) -> CollectorObservation:
            assert action == "extract_structured"
            assert args["competitor_id"] == "comp_cursor"
            assert args["dimension"] == "pricing"
            return CollectorObservation(
                channel="extract_structured",
                args=args,
                result=ToolObservationResult(
                    snippets=[
                        CollectorSnippet(
                            quote="Cursor starts at $20 per user/month.",
                            sanitized_text="Cursor starts at $20 per user/month.",
                            source_url="https://cursor.com/pricing",
                            source_title="Cursor Pricing",
                            source_type="pricing_page",
                            desensitized=False,
                            metadata={"dimension": "pricing", "competitor_id": "comp_cursor"},
                        )
                    ],
                    metadata={"dimension": "pricing", "competitor_id": "comp_cursor"},
                ),
            )

    monkeypatch.setattr("agents.subgraphs.researcher.get_channel_registry", lambda: _FakeRegistry())

    output = await get_researcher_subgraph().ainvoke(_base_state())
    drafts = output["evidence_drafts"]
    assert len(drafts) == 1
    assert drafts[0]["quote"] in known_quotes
    assert drafts[0]["source_url"] == "https://cursor.com/pricing"
    assert output["turn_count"] >= 1


@pytest.mark.asyncio
async def test_source_first_guard_overrides_llm_search_with_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_researcher_subgraph.cache_clear()
    fake_client = _FakeSequentialLLMClient(
        responses_by_slot={
            "research": [
                _llm_response(
                    "research",
                    {
                        "action": "search_web",
                        "action_args": {
                            "query": "cursor pricing",
                            "dimension": "pricing",
                        },
                        "reasoning_summary": "search first",
                    },
                ),
                _llm_response(
                    "research",
                    {
                        "action": "finalize",
                        "action_args": {"summary": "done"},
                        "reasoning_summary": "enough",
                    },
                ),
            ]
        }
    )
    monkeypatch.setattr("service.llm.harness.get_llm_client", lambda: fake_client)

    class _FakeRegistry:
        async def invoke(self, action: str, *, args: dict[str, object]) -> CollectorObservation:
            assert action == "fetch_url"
            assert args["url"] == "https://cursor.com/pricing"
            return CollectorObservation(
                channel="fetch_url",
                args=args,
                result=ToolObservationResult(
                    snippets=[
                        CollectorSnippet(
                            quote="Cursor pricing starts at $20 per user/month.",
                            sanitized_text="Cursor pricing starts at $20 per user/month.",
                            source_url="https://cursor.com/pricing",
                            source_title="Cursor Pricing",
                            source_type="pricing_page",
                            desensitized=False,
                            metadata={"dimension": "pricing", "competitor_id": "comp_cursor"},
                        )
                    ],
                    metadata={"dimension": "pricing", "competitor_id": "comp_cursor"},
                ),
            )

    monkeypatch.setattr("agents.subgraphs.researcher.get_channel_registry", lambda: _FakeRegistry())
    state = _base_state()
    state["resolved_official_urls"] = ["https://cursor.com/pricing"]
    state["resolved_official_hosts"] = ["cursor.com"]
    state["resolved_source_pages"] = [
        {"url": "https://cursor.com/pricing", "source_type": "pricing_page"}
    ]

    output = await get_researcher_subgraph().ainvoke(state)
    assert output["search_call_count"] == 0
    assert output["official_fetch_count"] == 1
    assert output["coverage_matrix"]["pricing"]["covered"] is True


@pytest.mark.asyncio
async def test_researcher_subgraph_triggers_compression(monkeypatch: pytest.MonkeyPatch) -> None:
    get_researcher_subgraph.cache_clear()
    fake_client = _FakeSequentialLLMClient(
        responses_by_slot={
            "compression": [
                _llm_response(
                    "compression",
                    {"compressed_summary": "compressed trace summary"},
                )
            ],
            "research": [
                _llm_response(
                    "research",
                    {
                        "action": "finalize",
                        "action_args": {"summary": "after compression"},
                        "reasoning_summary": "finish",
                    },
                )
            ],
        }
    )
    monkeypatch.setattr("service.llm.harness.get_llm_client", lambda: fake_client)

    state = _base_state()
    state["turn_count"] = COMPRESS_AFTER_TURNS
    state["messages"] = [{"role": "user", "content": "x" * 1500}, {"role": "assistant", "content": "y" * 1500}]
    state["pending_dimensions"] = []
    state["focus_dimensions"] = []

    output = await get_researcher_subgraph().ainvoke(state)
    assert output["compression_count"] >= 1
    assert any(item.get("model_slot") == "compression" for item in output["llm_calls"])
    assert output["messages"][1]["content"] == "compressed trace summary"


@pytest.mark.asyncio
async def test_researcher_subgraph_forces_finalize_when_turn_limit_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_researcher_subgraph.cache_clear()
    fake_client = _FakeSequentialLLMClient(responses_by_slot={"research": []})
    monkeypatch.setattr("service.llm.harness.get_llm_client", lambda: fake_client)

    state = _base_state()
    state["turn_count"] = 1
    state["max_turns"] = 1

    output = await get_researcher_subgraph().ainvoke(state)
    assert output["pending_action_args"] == {}
    assert output["next_action"] == "finalize"
    assert output["final_summary"]
    assert output["llm_calls"] == []
