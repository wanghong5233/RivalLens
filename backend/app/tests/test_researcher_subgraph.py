from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.subgraphs.researcher import (
    COMPRESS_AFTER_TURNS,
    ResearcherSubState,
    get_researcher_subgraph,
)
from agents.tools.pack_lookup import ToolObservation
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
    ) -> LLMResponse:
        del system_prompt, user_prompt, prompt
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
        "run_id": "run_test",
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


@pytest.mark.asyncio
async def test_researcher_subgraph_collects_evidence_from_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeSequentialLLMClient(
        responses_by_slot={
            "research": [
                _llm_response(
                    "research",
                    {
                        "action": "pack_lookup",
                        "action_args": {"competitor_id": "comp_cursor", "dimension": "pricing"},
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
    monkeypatch.setattr("agents.subgraphs.researcher.get_llm_client", lambda: fake_client)

    known_quotes = {"Cursor starts at $20 per user/month."}

    def _fake_pack_lookup(
        *,
        industry_pack_id: str,
        competitor_id: str,
        dimension: str,
    ) -> ToolObservation:
        assert industry_pack_id == "ai_coding_tools"
        assert competitor_id == "comp_cursor"
        assert dimension == "pricing"
        return ToolObservation(
            tool="pack_lookup",
            args={"industry_pack_id": industry_pack_id, "competitor_id": competitor_id, "dimension": dimension},
            result={
                "industry_pack_id": industry_pack_id,
                "competitor_id": competitor_id,
                "dimension": dimension,
                "snippets": [
                    {
                        "quote": "Cursor starts at $20 per user/month.",
                        "source_url": "https://cursor.com/pricing",
                        "source_title": "Cursor Pricing",
                        "desensitized": True,
                    }
                ],
            },
        )

    monkeypatch.setattr("agents.subgraphs.researcher.pack_lookup", _fake_pack_lookup)

    output = await get_researcher_subgraph().ainvoke(_base_state())
    drafts = output["evidence_drafts"]
    assert len(drafts) == 1
    assert drafts[0]["quote"] in known_quotes
    assert drafts[0]["source_url"] == "https://cursor.com/pricing"
    assert output["turn_count"] >= 1


@pytest.mark.asyncio
async def test_researcher_subgraph_triggers_compression(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr("agents.subgraphs.researcher.get_llm_client", lambda: fake_client)

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
    fake_client = _FakeSequentialLLMClient(responses_by_slot={"research": []})
    monkeypatch.setattr("agents.subgraphs.researcher.get_llm_client", lambda: fake_client)

    state = _base_state()
    state["turn_count"] = 1
    state["max_turns"] = 1

    output = await get_researcher_subgraph().ainvoke(state)
    assert output["pending_action_args"]["summary"] == "max researcher turns hit, force finalize"
    assert output["llm_calls"] == []
