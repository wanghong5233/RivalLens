from __future__ import annotations

from types import SimpleNamespace

import pytest

from service.llm import providers as llm_providers
from service.llm.exceptions import LLMRequestError
from service.llm.providers import DoubaoProvider, OpenAIProvider, QwenProvider


def _fake_response(*, model: str, content: str, prompt_tokens: int, completion_tokens: int):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


@pytest.mark.asyncio
async def test_doubao_provider_complete_json_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(**_: object):
        return _fake_response(
            model="doubao-seed",
            content='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"done"}',
            prompt_tokens=12,
            completion_tokens=6,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = DoubaoProvider(
        base_url="https://ark.example.com/v3",
        api_key="fake-key",
        default_model="ep-demo",
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="ep-demo",
        timeout_seconds=10,
    )

    assert response.model_name == "doubao-seed"
    assert response.prompt_tokens == 12
    assert response.completion_tokens == 6
    assert response.content_raw.startswith('{"chosen_tool"')


@pytest.mark.asyncio
async def test_doubao_provider_wraps_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConnectionError(Exception):
        pass

    async def fake_create(**_: object):
        raise DummyConnectionError("network down")

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "APIConnectionError", DummyConnectionError)
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = DoubaoProvider(
        base_url="https://ark.example.com/v3",
        api_key="fake-key",
        default_model="ep-demo",
    )
    with pytest.raises(LLMRequestError):
        await provider.complete_json(
            system_prompt="system",
            user_prompt="user",
            model="ep-demo",
            timeout_seconds=10,
        )


@pytest.mark.asyncio
async def test_doubao_provider_skips_json_mode_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_providers.clear_json_mode_capability_cache()
    call_kwargs: list[dict[str, object]] = []

    async def fake_create(**kwargs: object):
        call_kwargs.append(dict(kwargs))
        return _fake_response(
            model="doubao-seed",
            content='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"done"}',
            prompt_tokens=12,
            completion_tokens=6,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = DoubaoProvider(
        base_url="https://ark.example.com/v3",
        api_key="fake-key",
        default_model="ep-demo",
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="ep-demo",
        timeout_seconds=10,
    )

    assert response.model_name == "doubao-seed"
    assert len(call_kwargs) == 1
    assert "response_format" not in call_kwargs[0]


@pytest.mark.asyncio
async def test_doubao_provider_caches_json_mode_unsupported_after_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_providers.clear_json_mode_capability_cache()

    class DummyStatusError(Exception):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.status_code = 400

    call_kwargs: list[dict[str, object]] = []

    async def fake_create(**kwargs: object):
        call_kwargs.append(dict(kwargs))
        if "response_format" in kwargs:
            raise DummyStatusError(
                "InvalidParameter: response_format.type json_object is not supported by this model"
            )
        return _fake_response(
            model="gpt-4o-mini",
            content='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"done"}',
            prompt_tokens=12,
            completion_tokens=6,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "APIStatusError", DummyStatusError)
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = OpenAIProvider(
        base_url="https://api.openai.com/v1",
        api_key="fake-key",
        default_model="gpt-4o-mini",
    )
    await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="gpt-4o-mini",
        timeout_seconds=10,
    )
    call_kwargs.clear()
    await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="gpt-4o-mini",
        timeout_seconds=10,
    )

    assert len(call_kwargs) == 1
    assert "response_format" not in call_kwargs[0]


@pytest.mark.asyncio
async def test_doubao_provider_fallbacks_when_json_mode_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doubao skips json_mode by default; no 400 probe round-trip."""
    llm_providers.clear_json_mode_capability_cache()

    call_kwargs: list[dict[str, object]] = []

    async def fake_create(**kwargs: object):
        call_kwargs.append(dict(kwargs))
        return _fake_response(
            model="doubao-seed",
            content='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"done"}',
            prompt_tokens=12,
            completion_tokens=6,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = DoubaoProvider(
        base_url="https://ark.example.com/v3",
        api_key="fake-key",
        default_model="ep-demo",
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="ep-demo",
        timeout_seconds=10,
    )

    assert response.model_name == "doubao-seed"
    assert len(call_kwargs) == 1
    assert "response_format" not in call_kwargs[0]


@pytest.mark.asyncio
async def test_doubao_provider_retries_on_generic_json_mode_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doubao never sends json_mode on first attempt."""
    llm_providers.clear_json_mode_capability_cache()

    call_kwargs: list[dict[str, object]] = []

    async def fake_create(**kwargs: object):
        call_kwargs.append(dict(kwargs))
        return _fake_response(
            model="doubao-seed",
            content='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"done"}',
            prompt_tokens=12,
            completion_tokens=6,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = DoubaoProvider(
        base_url="https://ark.example.com/v3",
        api_key="fake-key",
        default_model="ep-demo",
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="ep-demo",
        timeout_seconds=10,
    )

    assert response.model_name == "doubao-seed"
    assert len(call_kwargs) == 1
    assert "response_format" not in call_kwargs[0]


@pytest.mark.asyncio
async def test_openai_provider_complete_json_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(**_: object):
        return _fake_response(
            model="gpt-4o-mini",
            content='{"chosen_tool":"Analyze","tool_args":{"parallel_by_dimension":false,"require_cross_competitor":true},"reasoning_summary":"analyze"}',
            prompt_tokens=20,
            completion_tokens=9,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = OpenAIProvider(
        base_url="https://api.openai.com/v1",
        api_key="fake-openai-key",
        default_model="gpt-4o-mini",
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="gpt-4o-mini",
        timeout_seconds=10,
    )

    assert response.model_name == "gpt-4o-mini"
    assert response.prompt_tokens == 20
    assert response.completion_tokens == 9
    assert response.content_raw.startswith('{"chosen_tool"')


@pytest.mark.asyncio
async def test_qwen_provider_complete_json_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(**_: object):
        return _fake_response(
            model="qwen-plus",
            content='{"chosen_tool":"Write","tool_args":{"style":"concise"},"reasoning_summary":"write"}',
            prompt_tokens=18,
            completion_tokens=8,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    provider = QwenProvider(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="fake-qwen-key",
        default_model="qwen-plus",
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        model="qwen-plus",
        timeout_seconds=10,
    )

    assert response.model_name == "qwen-plus"
    assert response.prompt_tokens == 18
    assert response.completion_tokens == 8
    assert response.content_raw.startswith('{"chosen_tool"')


def test_provider_default_model_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=None)))
    monkeypatch.setattr(llm_providers, "AsyncOpenAI", lambda **_: fake_client)

    doubao = DoubaoProvider(
        base_url="https://ark.example.com/v3",
        api_key="fake-key",
        default_model="ep-demo",
    )
    openai_provider = OpenAIProvider(
        base_url="https://api.openai.com/v1",
        api_key="fake-openai-key",
        default_model="gpt-4o-mini",
    )
    qwen_provider = QwenProvider(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="fake-qwen-key",
        default_model="qwen-plus",
    )

    assert doubao.default_model == "ep-demo"
    assert openai_provider.default_model == "gpt-4o-mini"
    assert qwen_provider.default_model == "qwen-plus"
