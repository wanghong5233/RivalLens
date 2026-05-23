from __future__ import annotations

import asyncio
import hashlib
import json
from json import JSONDecodeError
from time import perf_counter

from core.config import settings
from service.llm.exceptions import LLMRequestError, LLMResponseFormatError
from service.llm.providers import LLMProvider, build_providers
from service.llm.response import LLMResponse
from service.llm.routing import resolve_slot

LEGACY_SYSTEM_PROMPT = "legacy_supervisor_prompt"


def _format_error(error: LLMRequestError | LLMResponseFormatError) -> str:
    error_message = str(error).strip()
    if not error_message:
        return type(error).__name__
    return f"{type(error).__name__}: {error_message[:300]}"


def _prompt_hash(*, system_prompt: str, user_prompt: str) -> str:
    return hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode("utf-8")).hexdigest()[:64]


def _prompt_preview(*, system_prompt: str, user_prompt: str) -> str:
    preview = f"{system_prompt}\n{user_prompt}".strip().replace("\n", "\\n")
    return preview[:256]


def _parse_json_object(content_raw: str) -> dict[str, object]:
    try:
        parsed = json.loads(content_raw)
    except JSONDecodeError as exc:
        raise LLMResponseFormatError("Provider returned invalid JSON content.") from exc

    if not isinstance(parsed, dict):
        raise LLMResponseFormatError("Provider returned non-object JSON.")
    return parsed


class LLMClient:
    def __init__(
        self,
        *,
        providers: dict[str, LLMProvider],
        max_retries: int,
        timeout_seconds: int,
        global_concurrency: int,
    ) -> None:
        self._providers = providers
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(global_concurrency)

    async def complete_json(
        self,
        *,
        model_slot: str = "research",
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        prompt: str | None = None,
    ) -> LLMResponse:
        if prompt is not None and system_prompt is None and user_prompt is None:
            # Keep old supervisor path stable until all callers are migrated.
            system_prompt = LEGACY_SYSTEM_PROMPT
            user_prompt = prompt
            return LLMResponse(
                model_slot=model_slot,
                provider="legacy_stub",
                model_name="legacy_stub",
                prompt_preview=_prompt_preview(system_prompt=system_prompt, user_prompt=user_prompt),
                prompt_hash=_prompt_hash(system_prompt=system_prompt, user_prompt=user_prompt),
                content={},
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=0,
                error=None,
            )

        if system_prompt is None or user_prompt is None:
            raise ValueError(
                "LLMClient.complete_json requires both system_prompt and user_prompt for provider mode."
            )

        prompt_hash = _prompt_hash(system_prompt=system_prompt, user_prompt=user_prompt)
        prompt_preview = _prompt_preview(system_prompt=system_prompt, user_prompt=user_prompt)
        provider_name, model_name = resolve_slot(slot=model_slot, providers=self._providers)
        provider = self._providers[provider_name]

        request_error: LLMRequestError | None = None
        for attempt_index in range(self._max_retries + 1):
            started_at = perf_counter()
            try:
                async with self._semaphore:
                    raw_response = await provider.complete_json(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        model=model_name,
                        timeout_seconds=self._timeout_seconds,
                    )
            except LLMRequestError as exc:
                request_error = exc
                if attempt_index < self._max_retries:
                    await asyncio.sleep(0.2 * (2**attempt_index))
                    continue
                elapsed_ms = int((perf_counter() - started_at) * 1000)
                return LLMResponse(
                    model_slot=model_slot,
                    provider=provider_name,
                    model_name=model_name,
                    prompt_preview=prompt_preview,
                    prompt_hash=prompt_hash,
                    content={},
                    prompt_tokens=None,
                    completion_tokens=None,
                    latency_ms=elapsed_ms,
                    error=_format_error(exc),
                )

            elapsed_ms = int((perf_counter() - started_at) * 1000)
            try:
                content = _parse_json_object(raw_response.content_raw)
            except LLMResponseFormatError as exc:
                return LLMResponse(
                    model_slot=model_slot,
                    provider=provider_name,
                    model_name=raw_response.model_name,
                    prompt_preview=prompt_preview,
                    prompt_hash=prompt_hash,
                    content={},
                    prompt_tokens=raw_response.prompt_tokens,
                    completion_tokens=raw_response.completion_tokens,
                    latency_ms=elapsed_ms,
                    error=_format_error(exc),
                )

            return LLMResponse(
                model_slot=model_slot,
                provider=provider_name,
                model_name=raw_response.model_name,
                prompt_preview=prompt_preview,
                prompt_hash=prompt_hash,
                content=content,
                prompt_tokens=raw_response.prompt_tokens,
                completion_tokens=raw_response.completion_tokens,
                latency_ms=elapsed_ms,
                error=None,
            )

        if request_error is None:
            raise RuntimeError("LLM request retry loop reached unreachable state.")

        return LLMResponse(
            model_slot=model_slot,
            provider=provider_name,
            model_name=model_name,
            prompt_preview=prompt_preview,
            prompt_hash=prompt_hash,
            content={},
            prompt_tokens=None,
            completion_tokens=None,
            latency_ms=None,
            error=_format_error(request_error),
        )


_module_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _module_llm_client
    if _module_llm_client is None:
        _module_llm_client = LLMClient(
            providers=build_providers(),
            max_retries=settings.LLM_MAX_RETRIES,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            global_concurrency=settings.LLM_GLOBAL_CONCURRENCY,
        )
    return _module_llm_client


def _reset_llm_client_for_tests() -> None:
    global _module_llm_client
    _module_llm_client = None


llm_client = get_llm_client()
