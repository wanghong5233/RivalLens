from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.subgraphs.researcher import (
    ResearcherSubState,
    get_researcher_subgraph,
)
from service.collector.base import CollectorObservation, CollectorSnippet, ToolObservationResult
from service.collector.errors import ChannelError
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
        "run_id": "run_test_dispatcher",
        "industry_pack_id": "ai_coding_tools",
        "research_topic": "cursor pricing",
        "competitor_id": "comp_cursor",
        "focus_dimensions": ["pricing"],
        "pending_dimensions": ["pricing"],
        "queried_dimensions": [],
        "pending_action_args": {},
        "turn_count": 0,
        "max_turns": 6,
        "compression_count": 0,
        "messages": [],
        "observations_log": [],
        "evidence_drafts": [],
        "llm_calls": [],
        "next_action": "tool_exec",
        "final_summary": "",
    }


class _FakeSuccessRegistry:
    async def invoke(self, action: str, *, args: dict[str, object]) -> CollectorObservation:
        assert action == "search_web"
        assert args.get("query") == "cursor pricing"
        return CollectorObservation(
            channel="search_web",
            args=args,
            result=ToolObservationResult(
                snippets=[
                    CollectorSnippet(
                        quote="Cursor pricing updated in release note.",
                        sanitized_text="Cursor pricing updated in release note.",
                        source_url="https://news.example.com/cursor-pricing",
                        source_title="news",
                        source_type="article",
                        desensitized=False,
                        metadata={"dimension": "pricing", "competitor_id": "comp_cursor"},
                    )
                ],
                metadata={"dimension": "pricing", "competitor_id": "comp_cursor"},
            ),
        )


class _FakeFailureRegistry:
    async def invoke(self, action: str, *, args: dict[str, object]) -> CollectorObservation:
        del action, args
        raise ChannelError("simulated channel failure")


@pytest.mark.asyncio
async def test_researcher_dispatcher_uses_registry_and_collects_source_type(
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
                        "action_args": {"query": "cursor pricing"},
                        "reasoning_summary": "collect latest external signal",
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
    monkeypatch.setattr("agents.subgraphs.researcher.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("agents.subgraphs.researcher.get_channel_registry", lambda: _FakeSuccessRegistry())

    output = await get_researcher_subgraph().ainvoke(_base_state())
    assert output["turn_count"] >= 1
    assert len(output["evidence_drafts"]) == 1
    assert output["evidence_drafts"][0]["source_type"] == "article"


@pytest.mark.asyncio
async def test_researcher_dispatcher_channel_failure_does_not_abort_run(
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
                        "action_args": {"query": "cursor pricing"},
                        "reasoning_summary": "try online source first",
                    },
                ),
                _llm_response(
                    "research",
                    {
                        "action": "finalize",
                        "action_args": {"summary": "finish with partial"},
                        "reasoning_summary": "fallback finalize",
                    },
                ),
            ]
        }
    )
    monkeypatch.setattr("agents.subgraphs.researcher.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("agents.subgraphs.researcher.get_channel_registry", lambda: _FakeFailureRegistry())

    output = await get_researcher_subgraph().ainvoke(_base_state())
    observation_rows = output["observations_log"]
    assert observation_rows
    assert "error" in observation_rows[0]
    assert output["final_summary"]
