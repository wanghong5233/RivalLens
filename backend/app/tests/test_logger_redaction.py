from __future__ import annotations

import pytest

from core.config import settings
from service.llm.client import LLMClient
from service.llm.response import ProviderRawResponse
from utils.logger import configure_logging


class _SingleResponseProvider:
    def __init__(self, response: ProviderRawResponse) -> None:
        self.default_model = "ep-default"
        self._response = response
        self.call_count = 0

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
        if self.call_count > 1:
            raise RuntimeError("Provider called more than once in redaction test.")
        return self._response


@pytest.mark.asyncio
async def test_llm_client_logs_redact_prompt_and_fake_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    monkeypatch.setattr(settings, "LLM_PROVIDER_RESEARCH", "doubao")
    monkeypatch.setattr(settings, "LLM_MODEL_RESEARCH", None)
    fake_key = "sk-test-FAKESECRET-12345"
    system_prompt = f"system prompt with secret {fake_key}"
    user_prompt = f"user prompt mirrors secret {fake_key}"
    provider = _SingleResponseProvider(
        ProviderRawResponse(
            content_raw='{"chosen_tool":"Finalize","tool_args":{"completion_reason":"all_dimensions_covered"},"reasoning_summary":"ok"}',
            model_name="ep-default",
            prompt_tokens=13,
            completion_tokens=4,
        )
    )
    client = LLMClient(
        providers={"doubao": provider},
        max_retries=0,
        timeout_seconds=5,
        global_concurrency=1,
    )

    _ = await client.complete_json(
        model_slot="research",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    logged = capsys.readouterr().out
    assert "llm.call.start" in logged
    assert "llm.call.finish" in logged
    assert fake_key not in logged
    assert system_prompt not in logged
    assert user_prompt not in logged
