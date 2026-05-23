from __future__ import annotations

from typing import Any, ClassVar, Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from core.config import settings
from service.llm.exceptions import LLMRequestError, LLMResponseFormatError
from service.llm.response import ProviderRawResponse


class LLMProvider(Protocol):
    name: ClassVar[str]
    default_model: str

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: int,
    ) -> ProviderRawResponse:
        ...


def _extract_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise LLMResponseFormatError("Provider response missing choices.")

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None:
        raise LLMResponseFormatError("Provider response missing message.")

    content = getattr(message, "content", None)
    if isinstance(content, str):
        content_str = content.strip()
        if not content_str:
            raise LLMResponseFormatError("Provider response content is empty.")
        return content_str

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_part = item.get("text")
                if isinstance(text_part, str):
                    parts.append(text_part)
                continue

            text_part = getattr(item, "text", None)
            if isinstance(text_part, str):
                parts.append(text_part)

        joined = "".join(parts).strip()
        if not joined:
            raise LLMResponseFormatError("Provider list content contains no text part.")
        return joined

    raise LLMResponseFormatError("Provider response content is not a supported type.")


def _extract_usage_tokens(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None

    prompt_tokens_raw = getattr(usage, "prompt_tokens", None)
    completion_tokens_raw = getattr(usage, "completion_tokens", None)
    prompt_tokens = int(prompt_tokens_raw) if isinstance(prompt_tokens_raw, int) else None
    completion_tokens = (
        int(completion_tokens_raw) if isinstance(completion_tokens_raw, int) else None
    )
    return prompt_tokens, completion_tokens


def _request_error_message(provider_name: str, model: str, exc: Exception) -> str:
    return f"{provider_name} request failed for model={model}: {exc}"


def _is_json_mode_unsupported(exc: APIStatusError) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code not in {400, 422}:
        return False

    message = str(exc).lower()
    return (
        "response_format" in message
        and "json_object" in message
        and ("not supported" in message or "invalidparameter" in message or "unsupported" in message)
    )


async def _create_completion(
    *,
    client: AsyncOpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: int,
    use_json_mode: bool,
) -> Any:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "timeout": timeout_seconds,
    }
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return await client.chat.completions.create(**kwargs)


class _OpenAICompatibleProvider:
    name: ClassVar[str] = "unknown"

    def __init__(self, *, base_url: str, api_key: str, default_model: str) -> None:
        self.default_model = default_model
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: int,
    ) -> ProviderRawResponse:
        try:
            response = await _create_completion(
                client=self._client,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_seconds=timeout_seconds,
                use_json_mode=True,
            )
        except APIStatusError as exc:
            if _is_json_mode_unsupported(exc):
                try:
                    response = await _create_completion(
                        client=self._client,
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        timeout_seconds=timeout_seconds,
                        use_json_mode=False,
                    )
                except (APIConnectionError, APITimeoutError, APIStatusError, RateLimitError) as fallback_exc:
                    raise LLMRequestError(
                        _request_error_message(self.name, model, fallback_exc)
                    ) from fallback_exc
            else:
                raise LLMRequestError(_request_error_message(self.name, model, exc)) from exc
        except (APIConnectionError, APITimeoutError, RateLimitError) as exc:
            raise LLMRequestError(_request_error_message(self.name, model, exc)) from exc

        content_raw = _extract_message_content(response)
        prompt_tokens, completion_tokens = _extract_usage_tokens(response)
        model_name_raw = getattr(response, "model", None)
        model_name = model_name_raw if isinstance(model_name_raw, str) else model

        return ProviderRawResponse(
            content_raw=content_raw,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )


class DoubaoProvider(_OpenAICompatibleProvider):
    name: ClassVar[str] = "doubao"


class OpenAIProvider(_OpenAICompatibleProvider):
    name: ClassVar[str] = "openai"


class QwenProvider(_OpenAICompatibleProvider):
    name: ClassVar[str] = "qwen"


def _configured_provider_names() -> set[str]:
    return {
        settings.LLM_PROVIDER_RESEARCH,
        settings.LLM_PROVIDER_SUMMARIZATION,
        settings.LLM_PROVIDER_COMPRESSION,
        settings.LLM_PROVIDER_QA,
        settings.LLM_PROVIDER_WRITER,
    }


def build_providers() -> dict[str, LLMProvider]:
    providers: dict[str, LLMProvider] = {}
    configured_names = _configured_provider_names()

    if "doubao" in configured_names:
        if not settings.DOUBAO_API_KEY:
            raise RuntimeError("DOUBAO_API_KEY is required when any slot uses doubao provider.")
        if not settings.DOUBAO_EP:
            raise RuntimeError("DOUBAO_EP is required when any slot uses doubao provider.")
        providers["doubao"] = DoubaoProvider(
            base_url=settings.DOUBAO_BASE_URL,
            api_key=settings.DOUBAO_API_KEY,
            default_model=settings.DOUBAO_EP,
        )

    if "openai" in configured_names:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required when any slot uses openai provider.")
        providers["openai"] = OpenAIProvider(
            base_url=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            default_model=settings.OPENAI_DEFAULT_MODEL,
        )

    if "qwen" in configured_names:
        if not settings.QWEN_API_KEY:
            raise RuntimeError("QWEN_API_KEY is required when any slot uses qwen provider.")
        providers["qwen"] = QwenProvider(
            base_url=settings.QWEN_BASE_URL,
            api_key=settings.QWEN_API_KEY,
            default_model=settings.QWEN_DEFAULT_MODEL,
        )

    return providers
