from __future__ import annotations

import asyncio
import hashlib
import json
import re
from json import JSONDecodeError
from time import perf_counter

from core.config import settings
from service.llm.exceptions import LLMRequestError, LLMResponseFormatError
from service.llm.providers import LLMProvider, build_providers
from service.llm.response import LLMResponse
from service.llm.routing import resolve_slot
from service.llm.trace import build_prompt_preview, build_prompt_trace_text, sanitize_trace_text
from utils.logger import get_logger

LEGACY_SYSTEM_PROMPT = "legacy_supervisor_prompt"
log = get_logger("service.llm.client")


def _format_error(error: LLMRequestError | LLMResponseFormatError) -> str:
    error_message = str(error).strip()
    if not error_message:
        return type(error).__name__
    return f"{type(error).__name__}: {error_message[:300]}"


def _prompt_hash(*, system_prompt: str, user_prompt: str) -> str:
    return hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode("utf-8")).hexdigest()[:64]


def _merge_request_errors(*, primary_error: Exception, fallback_error: Exception | None) -> str:
    primary = _format_error(LLMRequestError(str(primary_error)))
    if fallback_error is None:
        return primary
    fallback = _format_error(LLMRequestError(str(fallback_error)))
    return f"primary={primary}; fallback={fallback}"


def _trim_for_log(value: str | None, *, limit: int = 200) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _resolve_timeout_seconds(model_slot: str) -> int:
    if model_slot == "writer":
        return settings.LLM_TIMEOUT_WRITER
    return settings.LLM_TIMEOUT_SECONDS


def _classify_llm_error(error: LLMRequestError | LLMResponseFormatError | str) -> str:
    message = str(error).lower()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "connection" in message:
        return "connection"
    if "400" in message or "422" in message or "bad request" in message:
        return "http_4xx"
    if isinstance(error, LLMResponseFormatError):
        return "format"
    return "unknown"


def _log_call_error(
    *,
    model_slot: str,
    provider: str,
    error: LLMRequestError | LLMResponseFormatError | str,
    attempt: int | None = None,
    retryable: bool = False,
) -> None:
    log.warning(
        "llm.call.error",
        model_slot=model_slot,
        provider=provider,
        error_class=_classify_llm_error(error),
        attempt=attempt,
        retryable=retryable,
        error=_trim_for_log(_format_error(error) if not isinstance(error, str) else error),
    )


def _log_finish(
    *,
    model_slot: str,
    provider: str,
    model_name: str | None,
    prompt_hash: str,
    prompt_preview_len: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int | None,
    error: str | None,
    fallback_used: bool,
    fallback_reason: str | None,
) -> None:
    log.info(
        "llm.call.finish",
        model_slot=model_slot,
        provider=provider,
        model_name=model_name,
        prompt_hash=prompt_hash,
        prompt_preview_len=prompt_preview_len,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        error=_trim_for_log(error),
        fallback_used=fallback_used,
        fallback_reason=_trim_for_log(fallback_reason),
    )


def _parse_json_object(content_raw: str) -> dict[str, object]:
    candidates: list[str] = [content_raw.strip()]
    fenced_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        content_raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced_match:
        candidates.append(fenced_match.group(1).strip())

    first_brace = content_raw.find("{")
    last_brace = content_raw.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(content_raw[first_brace : last_brace + 1].strip())

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    raise LLMResponseFormatError("Provider returned invalid JSON object content.")


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
        fallback_system_prompt: str | None = None,
        fallback_user_prompt: str | None = None,
    ) -> LLMResponse:
        if prompt is not None and system_prompt is None and user_prompt is None:
            # Keep old supervisor path stable until all callers are migrated.
            system_prompt = LEGACY_SYSTEM_PROMPT
            user_prompt = prompt
            prompt_text = build_prompt_trace_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            prompt_preview = build_prompt_preview(prompt_text)
            log.debug(
                "llm.call.start",
                model_slot=model_slot,
                provider_target="legacy_stub",
                prompt_hash=_prompt_hash(system_prompt=system_prompt, user_prompt=user_prompt),
                prompt_preview_len=len(prompt_preview),
                fallback_configured=False,
            )
            response = LLMResponse(
                model_slot=model_slot,
                provider="legacy_stub",
                model_name="legacy_stub",
                prompt_preview=prompt_preview,
                prompt_hash=_prompt_hash(system_prompt=system_prompt, user_prompt=user_prompt),
                content={},
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=0,
                error=None,
                prompt_text=prompt_text,
            )
            _log_finish(
                model_slot=model_slot,
                provider=response.provider,
                model_name=response.model_name,
                prompt_hash=response.prompt_hash,
                prompt_preview_len=len(response.prompt_preview),
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                latency_ms=response.latency_ms,
                error=response.error,
                fallback_used=response.fallback_used,
                fallback_reason=response.fallback_reason,
            )
            return response

        if system_prompt is None or user_prompt is None:
            raise ValueError(
                "LLMClient.complete_json requires both system_prompt and user_prompt for provider mode."
            )
        if (fallback_system_prompt is None) ^ (fallback_user_prompt is None):
            raise ValueError(
                "LLMClient.complete_json requires fallback_system_prompt and fallback_user_prompt "
                "to be set together."
            )

        prompt_hash = _prompt_hash(system_prompt=system_prompt, user_prompt=user_prompt)
        prompt_text = build_prompt_trace_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        prompt_preview = build_prompt_preview(prompt_text)
        provider_name, model_name = resolve_slot(slot=model_slot, providers=self._providers)
        provider = self._providers[provider_name]
        slot_timeout_seconds = _resolve_timeout_seconds(model_slot)
        log.debug(
            "llm.call.start",
            model_slot=model_slot,
            provider_target=provider_name,
            prompt_hash=prompt_hash,
            prompt_preview_len=len(prompt_preview),
            fallback_configured=fallback_system_prompt is not None,
            timeout_seconds=slot_timeout_seconds,
        )

        request_error: LLMRequestError | None = None
        elapsed_ms: int | None = None
        for attempt_index in range(self._max_retries + 1):
            started_at = perf_counter()
            try:
                async with self._semaphore:
                    raw_response = await provider.complete_json(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        model=model_name,
                        timeout_seconds=slot_timeout_seconds,
                    )
            except LLMRequestError as exc:
                request_error = exc
                elapsed_ms = int((perf_counter() - started_at) * 1000)
                log.info(
                    "llm.call.retry",
                    model_slot=model_slot,
                    provider=provider_name,
                    attempt=attempt_index + 1,
                    max_attempts=self._max_retries + 1,
                    latency_ms=elapsed_ms,
                    error=_trim_for_log(_format_error(exc)),
                )
                if attempt_index < self._max_retries:
                    await asyncio.sleep(0.2 * (2**attempt_index))
                    continue
                break

            elapsed_ms = int((perf_counter() - started_at) * 1000)
            try:
                content = _parse_json_object(raw_response.content_raw)
            except LLMResponseFormatError as exc:
                _log_call_error(
                    model_slot=model_slot,
                    provider=provider_name,
                    error=exc,
                    attempt=attempt_index + 1,
                    retryable=False,
                )
                response = LLMResponse(
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
                    prompt_text=prompt_text,
                    response_raw=sanitize_trace_text(raw_response.content_raw),
                )
                _log_finish(
                    model_slot=model_slot,
                    provider=response.provider,
                    model_name=response.model_name,
                    prompt_hash=response.prompt_hash,
                    prompt_preview_len=len(response.prompt_preview),
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    latency_ms=response.latency_ms,
                    error=response.error,
                    fallback_used=response.fallback_used,
                    fallback_reason=response.fallback_reason,
                )
                return response

            response = LLMResponse(
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
                prompt_text=prompt_text,
                response_raw=sanitize_trace_text(raw_response.content_raw),
            )
            _log_finish(
                model_slot=model_slot,
                provider=response.provider,
                model_name=response.model_name,
                prompt_hash=response.prompt_hash,
                prompt_preview_len=len(response.prompt_preview),
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                latency_ms=response.latency_ms,
                error=response.error,
                fallback_used=response.fallback_used,
                fallback_reason=response.fallback_reason,
            )
            return response

        if request_error is not None and fallback_system_prompt is not None and fallback_user_prompt is not None:
            fallback_prompt_hash = _prompt_hash(
                system_prompt=fallback_system_prompt,
                user_prompt=fallback_user_prompt,
            )
            fallback_prompt_text = build_prompt_trace_text(
                system_prompt=fallback_system_prompt,
                user_prompt=fallback_user_prompt,
            )
            fallback_prompt_preview = build_prompt_preview(fallback_prompt_text)
            formatted_primary_error = _format_error(request_error)
            log.info(
                "llm.call.fallback",
                model_slot=model_slot,
                provider=provider_name,
                reason=_trim_for_log(formatted_primary_error),
            )
            started_at = perf_counter()
            try:
                async with self._semaphore:
                    raw_response = await provider.complete_json(
                        system_prompt=fallback_system_prompt,
                        user_prompt=fallback_user_prompt,
                        model=model_name,
                        timeout_seconds=slot_timeout_seconds,
                    )
            except LLMRequestError as fallback_exc:
                fallback_elapsed_ms = int((perf_counter() - started_at) * 1000)
                _log_call_error(
                    model_slot=model_slot,
                    provider=provider_name,
                    error=fallback_exc,
                    attempt=self._max_retries + 2,
                    retryable=False,
                )
                response = LLMResponse(
                    model_slot=model_slot,
                    provider=provider_name,
                    model_name=model_name,
                    prompt_preview=fallback_prompt_preview,
                    prompt_hash=fallback_prompt_hash,
                    content={},
                    prompt_tokens=None,
                    completion_tokens=None,
                    latency_ms=fallback_elapsed_ms,
                    error=_merge_request_errors(
                        primary_error=request_error,
                        fallback_error=fallback_exc,
                    ),
                    fallback_used=True,
                    fallback_reason=formatted_primary_error,
                    prompt_text=fallback_prompt_text,
                )
                _log_finish(
                    model_slot=model_slot,
                    provider=response.provider,
                    model_name=response.model_name,
                    prompt_hash=response.prompt_hash,
                    prompt_preview_len=len(response.prompt_preview),
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    latency_ms=response.latency_ms,
                    error=response.error,
                    fallback_used=response.fallback_used,
                    fallback_reason=response.fallback_reason,
                )
                return response

            fallback_elapsed_ms = int((perf_counter() - started_at) * 1000)
            try:
                content = _parse_json_object(raw_response.content_raw)
            except LLMResponseFormatError as exc:
                _log_call_error(
                    model_slot=model_slot,
                    provider=provider_name,
                    error=exc,
                    attempt=self._max_retries + 2,
                    retryable=False,
                )
                response = LLMResponse(
                    model_slot=model_slot,
                    provider=provider_name,
                    model_name=raw_response.model_name,
                    prompt_preview=fallback_prompt_preview,
                    prompt_hash=fallback_prompt_hash,
                    content={},
                    prompt_tokens=raw_response.prompt_tokens,
                    completion_tokens=raw_response.completion_tokens,
                    latency_ms=fallback_elapsed_ms,
                    error=_format_error(exc),
                    fallback_used=True,
                    fallback_reason=formatted_primary_error,
                    prompt_text=fallback_prompt_text,
                    response_raw=sanitize_trace_text(raw_response.content_raw),
                )
                _log_finish(
                    model_slot=model_slot,
                    provider=response.provider,
                    model_name=response.model_name,
                    prompt_hash=response.prompt_hash,
                    prompt_preview_len=len(response.prompt_preview),
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    latency_ms=response.latency_ms,
                    error=response.error,
                    fallback_used=response.fallback_used,
                    fallback_reason=response.fallback_reason,
                )
                return response

            response = LLMResponse(
                model_slot=model_slot,
                provider=provider_name,
                model_name=raw_response.model_name,
                prompt_preview=fallback_prompt_preview,
                prompt_hash=fallback_prompt_hash,
                content=content,
                prompt_tokens=raw_response.prompt_tokens,
                completion_tokens=raw_response.completion_tokens,
                latency_ms=fallback_elapsed_ms,
                error=None,
                fallback_used=True,
                fallback_reason=formatted_primary_error,
                prompt_text=fallback_prompt_text,
                response_raw=sanitize_trace_text(raw_response.content_raw),
            )
            _log_finish(
                model_slot=model_slot,
                provider=response.provider,
                model_name=response.model_name,
                prompt_hash=response.prompt_hash,
                prompt_preview_len=len(response.prompt_preview),
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                latency_ms=response.latency_ms,
                error=response.error,
                fallback_used=response.fallback_used,
                fallback_reason=response.fallback_reason,
            )
            return response

        if request_error is None:
            raise RuntimeError("LLM request retry loop reached unreachable state.")

        _log_call_error(
            model_slot=model_slot,
            provider=provider_name,
            error=request_error,
            attempt=self._max_retries + 1,
            retryable=False,
        )
        response = LLMResponse(
            model_slot=model_slot,
            provider=provider_name,
            model_name=model_name,
            prompt_preview=prompt_preview,
            prompt_hash=prompt_hash,
            content={},
            prompt_tokens=None,
            completion_tokens=None,
            latency_ms=elapsed_ms,
            error=_format_error(request_error),
            prompt_text=prompt_text,
        )
        _log_finish(
            model_slot=model_slot,
            provider=response.provider,
            model_name=response.model_name,
            prompt_hash=response.prompt_hash,
            prompt_preview_len=len(response.prompt_preview),
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            error=response.error,
            fallback_used=response.fallback_used,
            fallback_reason=response.fallback_reason,
        )
        return response


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
