from __future__ import annotations

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

    def override_response(self, response: LLMResponse) -> None:
        self._response = response

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
        del (
            system_prompt,
            user_prompt,
            prompt,
            fallback_system_prompt,
            fallback_user_prompt,
        )
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
