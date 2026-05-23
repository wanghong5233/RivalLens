from __future__ import annotations

import asyncio

import pytest

from core.config import settings
from service.llm.client import LLMClient
from service.llm.exceptions import LLMRequestError
from service.llm.response import ProviderRawResponse


class _SequencedProvider:
    def __init__(
        self,
        *,
        default_model: str,
        responses: list[ProviderRawResponse],
        request_errors: list[LLMRequestError] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.default_model = default_model
        self._responses = responses
        self._request_errors = request_errors or []
        self._delay_seconds = delay_seconds
        self.call_count = 0
        self.inflight = 0
        self.max_inflight = 0

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: int,
    ) -> ProviderRawResponse:
        del system_prompt, user_prompt, model, timeout_seconds
        self.call_count += 1
        self.inflight += 1
        if self.inflight > self.max_inflight:
            self.max_inflight = self.inflight
        try:
            if self._delay_seconds > 0:
                await asyncio.sleep(self._delay_seconds)

            if self._request_errors:
                raise self._request_errors.pop(0)

            if not self._responses:
                raise RuntimeError("No fake response configured for provider test.")
            return self._responses.pop(0)
        finally:
            self.inflight -= 1


def _make_client(provider: _SequencedProvider, *, max_retries: int = 2, concurrency: int = 2) -> LLMClient:
    return LLMClient(
        providers={"doubao": provider},
        max_retries=max_retries,
        timeout_seconds=10,
        global_concurrency=concurrency,
    )


def _mock_research_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER_RESEARCH", "doubao")
    monkeypatch.setattr(settings, "LLM_MODEL_RESEARCH", None)


@pytest.mark.asyncio
async def test_llm_client_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[
            ProviderRawResponse(
                content_raw='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"done"}',
                model_name="ep-default",
                prompt_tokens=9,
                completion_tokens=3,
            )
        ],
    )
    client = _make_client(provider)
    response = await client.complete_json(
        model_slot="research",
        system_prompt="system",
        user_prompt="user",
    )

    assert response.error is None
    assert response.provider == "doubao"
    assert response.model_name == "ep-default"
    assert response.prompt_tokens == 9
    assert response.completion_tokens == 3
    assert response.content["chosen_tool"] == "Finalize"


@pytest.mark.asyncio
async def test_llm_client_json_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[
            ProviderRawResponse(
                content_raw="not-a-json-object",
                model_name="ep-default",
                prompt_tokens=10,
                completion_tokens=2,
            )
        ],
    )
    client = _make_client(provider)
    response = await client.complete_json(
        model_slot="research",
        system_prompt="system",
        user_prompt="user",
    )

    assert response.content == {}
    assert response.error is not None
    assert "LLMResponseFormatError" in response.error


@pytest.mark.asyncio
async def test_llm_client_retries_on_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[
            ProviderRawResponse(
                content_raw='{"chosen_tool":"Analyze","tool_args":{"parallel_by_dimension":false,"require_cross_competitor":true},"reasoning_summary":"next"}',
                model_name="ep-default",
                prompt_tokens=11,
                completion_tokens=4,
            )
        ],
        request_errors=[
            LLMRequestError("first failed"),
            LLMRequestError("second failed"),
        ],
    )
    client = _make_client(provider, max_retries=2)
    response = await client.complete_json(
        model_slot="research",
        system_prompt="system",
        user_prompt="user",
    )

    assert provider.call_count == 3
    assert response.error is None
    assert response.content["chosen_tool"] == "Analyze"


@pytest.mark.asyncio
async def test_llm_client_uses_fallback_prompt_after_primary_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[
            ProviderRawResponse(
                content_raw='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"fallback"}',
                model_name="ep-default",
                prompt_tokens=7,
                completion_tokens=2,
            )
        ],
        request_errors=[
            LLMRequestError("primary failed once"),
            LLMRequestError("primary failed twice"),
        ],
    )
    client = _make_client(provider, max_retries=1)
    response = await client.complete_json(
        model_slot="research",
        system_prompt="system",
        user_prompt="user",
        fallback_system_prompt="fallback-system",
        fallback_user_prompt="fallback-user",
    )

    assert provider.call_count == 3
    assert response.error is None
    assert response.fallback_used is True
    assert response.fallback_reason is not None
    assert response.content["chosen_tool"] == "Finalize"


@pytest.mark.asyncio
async def test_llm_client_returns_error_when_fallback_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[],
        request_errors=[
            LLMRequestError("primary failed once"),
            LLMRequestError("primary failed twice"),
            LLMRequestError("fallback failed"),
        ],
    )
    client = _make_client(provider, max_retries=1)
    response = await client.complete_json(
        model_slot="research",
        system_prompt="system",
        user_prompt="user",
        fallback_system_prompt="fallback-system",
        fallback_user_prompt="fallback-user",
    )

    assert provider.call_count == 3
    assert response.error is not None
    assert "primary=" in response.error
    assert "fallback=" in response.error
    assert response.fallback_used is True


@pytest.mark.asyncio
async def test_llm_client_prompt_hash_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[
            ProviderRawResponse(
                content_raw='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"a"}',
                model_name="ep-default",
                prompt_tokens=1,
                completion_tokens=1,
            ),
            ProviderRawResponse(
                content_raw='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"b"}',
                model_name="ep-default",
                prompt_tokens=1,
                completion_tokens=1,
            ),
        ],
    )
    client = _make_client(provider)
    first = await client.complete_json(
        model_slot="research",
        system_prompt="same-system",
        user_prompt="same-user",
    )
    second = await client.complete_json(
        model_slot="research",
        system_prompt="same-system",
        user_prompt="same-user",
    )

    assert first.prompt_hash == second.prompt_hash


@pytest.mark.asyncio
async def test_llm_client_semaphore_limits_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_research_slot(monkeypatch)
    provider = _SequencedProvider(
        default_model="ep-default",
        responses=[
            ProviderRawResponse(
                content_raw='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"ok"}',
                model_name="ep-default",
                prompt_tokens=1,
                completion_tokens=1,
            )
            for _ in range(8)
        ],
        delay_seconds=0.05,
    )
    client = _make_client(provider, concurrency=2)

    await asyncio.gather(
        *[
            client.complete_json(
                model_slot="research",
                system_prompt="system",
                user_prompt=f"user-{index}",
            )
            for index in range(8)
        ]
    )

    assert provider.max_inflight <= 2
