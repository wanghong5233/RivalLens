from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app_main import app
from service.llm.response import LLMResponse


class _FakeLLMClient:
    def __init__(self) -> None:
        self._response = LLMResponse(
            model_slot="research",
            provider="fake_llm",
            model_name="fake-research-model",
            prompt_preview="fake-prompt-preview",
            prompt_hash="fake_prompt_hash",
            content={},
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            error=None,
        )
        self._override_enabled = False
        self._supervisor_call_count = 0

    def override_response(self, response: LLMResponse) -> None:
        self._response = response
        self._override_enabled = True

    @staticmethod
    def _extract_json_value(user_prompt: str, field_name: str) -> object | None:
        matched = re.search(rf"- {field_name}: ([^\n]*)", user_prompt)
        if matched is None:
            return None
        raw_value = matched.group(1)
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_json_list(user_prompt: str, field_name: str) -> list[str]:
        parsed = _FakeLLMClient._extract_json_value(user_prompt, field_name)
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, str)]

    def _build_response(self, *, model_slot: str, content: dict[str, object]) -> LLMResponse:
        return LLMResponse(
            model_slot=model_slot,
            provider=self._response.provider,
            model_name=self._response.model_name,
            prompt_preview=self._response.prompt_preview,
            prompt_hash=self._response.prompt_hash,
            content=content,
            prompt_tokens=self._response.prompt_tokens,
            completion_tokens=self._response.completion_tokens,
            latency_ms=self._response.latency_ms,
            error=None,
        )

    def _build_supervisor_decision_response(self, user_prompt: str) -> LLMResponse:
        pending_competitors = self._extract_json_list(user_prompt, "pending_competitors")
        analysis_done = "- analysis_done: True" in user_prompt
        report_draft_done = "- report_draft_done: True" in user_prompt

        if self._supervisor_call_count == 0 and len(pending_competitors) >= 2:
            topics: list[dict[str, object]] = []
            for competitor_id in pending_competitors:
                topics.append(
                    {
                        "research_topic": f"{competitor_id} vs user_query=fake",
                        "competitor_id": competitor_id,
                        "focus_dimensions": ["feature", "pricing", "user_feedback"],
                        "max_iterations": 6,
                        "fallback_to_offline": True,
                    }
                )
            content: dict[str, object] = {
                "chosen_tool": "ConductResearchBatch",
                "tool_args": {
                    "topics": topics,
                    "parallelism_rationale": "parallelize independent competitor research",
                },
                "reasoning_summary": "Batch pending competitors in one decision for faster completion.",
            }
        elif pending_competitors:
            competitor_id = pending_competitors[0]
            content = {
                "chosen_tool": "ConductResearch",
                "tool_args": {
                    "research_topic": f"{competitor_id} vs user_query=fake",
                    "competitor_id": competitor_id,
                    "focus_dimensions": ["feature", "pricing", "user_feedback"],
                    "max_iterations": 6,
                    "fallback_to_offline": True,
                },
                "reasoning_summary": "Select next pending competitor for research.",
            }
        elif not analysis_done:
            content = {
                "chosen_tool": "Analyze",
                "tool_args": {
                    "focus_dimensions": ["feature", "pricing", "user_feedback"],
                    "parallel_by_dimension": False,
                    "require_cross_competitor": True,
                },
                "reasoning_summary": "All competitors researched; move to analysis.",
            }
        elif not report_draft_done:
            content = {
                "chosen_tool": "Write",
                "tool_args": {
                    "template_id": "battlecard_default",
                    "sections": ["feature", "pricing", "user_feedback", "differentiation", "swot"],
                },
                "reasoning_summary": "Analysis completed; move to writer.",
            }
        else:
            content = {
                "chosen_tool": "Finalize",
                "tool_args": {
                    "completion_reason": "all_dimensions_covered",
                    "notes": "Done",
                },
                "reasoning_summary": "Workflow completed.",
            }
        self._supervisor_call_count += 1
        return self._build_response(model_slot="research", content=content)

    def _build_writer_response(self, user_prompt: str) -> LLMResponse:
        template_id_match = re.search(r"- template_id: ([^\n]+)", user_prompt)
        template_id = template_id_match.group(1).strip() if template_id_match is not None else "battlecard_default"
        requested_sections = self._extract_json_list(user_prompt, "requested_sections")
        evidence_briefs_raw = self._extract_json_value(user_prompt, "evidence_briefs")
        if isinstance(evidence_briefs_raw, list):
            evidence_ids = [
                item["evidence_id"]
                for item in evidence_briefs_raw
                if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
            ]
        else:
            evidence_ids = []
        analyst_insights_raw = self._extract_json_value(user_prompt, "analyst_insights")
        if isinstance(analyst_insights_raw, list):
            analyst_insights = [item for item in analyst_insights_raw if isinstance(item, dict)]
        else:
            analyst_insights = []
        risk_flags = self._extract_json_list(user_prompt, "risk_flags")
        analyst_summary_match = re.search(r"- analyst_summary: ([^\n]*)", user_prompt)
        analyst_summary = (
            analyst_summary_match.group(1).strip()
            if analyst_summary_match is not None and analyst_summary_match.group(1).strip()
            else "Summary generated by fake writer client."
        )

        if not requested_sections:
            requested_sections = ["feature", "pricing", "user_feedback"]
        if not evidence_ids:
            evidence_ids = ["ev_fake_001"]

        section_title_map = {
            "feature": "Feature Comparison",
            "pricing": "Pricing Strategy",
            "user_feedback": "User Feedback Signals",
            "differentiation": "Differentiation",
            "swot": "SWOT Snapshot",
        }
        sections: list[dict[str, object]] = []
        for section_id in requested_sections:
            section_insights = [
                item
                for item in analyst_insights
                if isinstance(item.get("dimension"), str) and item.get("dimension") == section_id
            ]
            if not section_insights:
                section_insights = analyst_insights[:1]
            evidence_refs: list[str] = []
            insight_refs: list[str] = []
            for item in section_insights:
                insight_id = item.get("insight_id")
                if isinstance(insight_id, str):
                    insight_refs.append(insight_id)
                evidence_ids_raw = item.get("evidence_ids")
                if isinstance(evidence_ids_raw, list):
                    evidence_refs.extend(
                        evidence_id
                        for evidence_id in evidence_ids_raw
                        if isinstance(evidence_id, str) and evidence_id in evidence_ids
                    )
            if not evidence_refs:
                evidence_refs = evidence_ids[:1]
            if not insight_refs:
                insight_refs = ["insight_1"]
            content_markdown = (
                "This section is generated by fake writer LLM for deterministic tests. "
                "It summarizes competitive signals and keeps evidence links for QA validation."
            )
            sections.append(
                {
                    "section_id": section_id,
                    "title": section_title_map.get(section_id, section_id.title()),
                    "content_markdown": content_markdown,
                    "evidence_refs": evidence_refs,
                    "insight_refs": insight_refs,
                }
            )

        content = {
            "template_id": template_id,
            "title": "RivalLens Test Battlecard",
            "executive_summary": analyst_summary,
            "sections": sections,
            "risk_callouts": risk_flags or ["fake_writer_mode"],
        }
        return self._build_response(model_slot="writer", content=content)

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
        del prompt, fallback_system_prompt, fallback_user_prompt
        if self._override_enabled:
            if self._response.model_slot == model_slot:
                return self._response
            return LLMResponse(
                model_slot=model_slot,
                provider=self._response.provider,
                model_name=self._response.model_name,
                prompt_preview=self._response.prompt_preview,
                prompt_hash=self._response.prompt_hash,
                content=self._response.content,
                prompt_tokens=self._response.prompt_tokens,
                completion_tokens=self._response.completion_tokens,
                latency_ms=self._response.latency_ms,
                error=self._response.error,
                fallback_used=self._response.fallback_used,
                fallback_reason=self._response.fallback_reason,
            )

        if (
            model_slot == "research"
            and isinstance(system_prompt, str)
            and "Supervisor planner" in system_prompt
            and isinstance(user_prompt, str)
            and "Planning context" in user_prompt
        ):
            return self._build_supervisor_decision_response(user_prompt)
        if (
            model_slot == "writer"
            and isinstance(system_prompt, str)
            and "RivalLens Writer" in system_prompt
            and isinstance(user_prompt, str)
            and "Writer context" in user_prompt
        ):
            return self._build_writer_response(user_prompt)

        if self._response.model_slot == model_slot:
            return self._response
        return LLMResponse(
            model_slot=model_slot,
            provider=self._response.provider,
            model_name=self._response.model_name,
            prompt_preview=self._response.prompt_preview,
            prompt_hash=self._response.prompt_hash,
            content=self._response.content,
            prompt_tokens=self._response.prompt_tokens,
            completion_tokens=self._response.completion_tokens,
            latency_ms=self._response.latency_ms,
            error=self._response.error,
            fallback_used=self._response.fallback_used,
            fallback_reason=self._response.fallback_reason,
        )


@pytest.fixture(autouse=True)
def fake_llm_client(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> _FakeLLMClient | None:
    node_path = str(request.node.path)
    if any(
        name in node_path
        for name in ("test_llm_client.py", "test_llm_providers.py", "test_llm_routing.py")
    ):
        return None

    fake_client = _FakeLLMClient()
    monkeypatch.setattr("service.llm.client.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("agents.nodes.supervisor.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("agents.nodes.analyst.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("agents.nodes.writer.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("agents.subgraphs.researcher.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("service.qa.engine.get_llm_client", lambda: fake_client)
    return fake_client


@pytest.fixture()
def override_llm_response(
    fake_llm_client: _FakeLLMClient | None,
) -> Callable[[LLMResponse], None]:
    if fake_llm_client is None:
        raise RuntimeError("override_llm_response fixture is unavailable for llm service tests.")

    def _override(response: LLMResponse) -> None:
        fake_llm_client.override_response(response)

    return _override


@pytest.fixture()
def test_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client
