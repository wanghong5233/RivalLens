from __future__ import annotations

import asyncio
from hashlib import sha256
import time
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from agents.tools.search_bocha import BochaSearchChannel
from agents.tools.search_serper import SerperSearchChannel
from agents.tools.search_web import TavilySearchChannel
from core.config import settings
from service.locale import country_for_language, plan_search_languages
from service.collector.base import (
    BaseChannel,
    CollectorObservation,
    CollectorSnippet,
    ToolObservationResult,
)
from service.collector.errors import ChannelError, FetchTimeout, RateLimited
from utils.logger import get_logger

log = get_logger("agents.tools.search_router")

ProviderName = Literal["bocha", "serper", "tavily"]
_MAX_ROUTER_LANGUAGES = 4


def _normalize_response_language(value: object) -> str | None:
    return value if isinstance(value, str) and value in {"zh", "en"} else None


def _provider_chain_for_language(
    language: str,
    *,
    explicit_country: str | None,
) -> tuple[tuple[ProviderName, str | None], ...]:
    country = explicit_country or country_for_language(language)
    # Serper (Google SERP) is the resilient primary for non-Chinese legs and a secondary
    # for Chinese after Bocha; it only enters the chain when its key is configured, so a
    # missing key leaves the original Bocha/Tavily behavior untouched. Tavily drops to
    # last resort everywhere once Serper is present.
    serper_leg: tuple[tuple[ProviderName, str | None], ...] = (
        (("serper", country),) if settings.SERPER_API_KEY else ()
    )
    if language == "zh":
        return (("bocha", None),) + serper_leg + (("tavily", country),)
    return serper_leg + (("tavily", country),)


def _explicit_search_languages(value: object, *, max_languages: int) -> list[str] | None:
    if not isinstance(value, list):
        return None
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        key = item.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
        if len(cleaned) >= max_languages:
            break
    return cleaned or None


def _query_variants(primary_query: str, raw_variants: object) -> list[str]:
    variants = [primary_query.strip()]
    if isinstance(raw_variants, list):
        variants.extend(item.strip() for item in raw_variants if isinstance(item, str) and item.strip())
    seen: set[str] = set()
    out: list[str] = []
    for item in variants:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[:3]


def _query_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _canonical_url(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip().casefold()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, "", ""))


def _dedupe_snippets(snippets: list[CollectorSnippet]) -> list[CollectorSnippet]:
    seen: set[str] = set()
    out: list[CollectorSnippet] = []
    for snippet in snippets:
        canonical = _canonical_url(snippet.source_url)
        key = canonical or sha256(snippet.sanitized_text.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(snippet)
    return out


class SearchWebRouterChannel(BaseChannel):
    name = "search_web"

    def __init__(
        self,
        *,
        bocha_channel: BochaSearchChannel | None = None,
        tavily_channel: TavilySearchChannel | None = None,
        serper_channel: SerperSearchChannel | None = None,
    ) -> None:
        self._bocha = bocha_channel or BochaSearchChannel()
        self._tavily = tavily_channel or TavilySearchChannel()
        self._serper = serper_channel or SerperSearchChannel()

    def _plan_legs(
        self,
        *,
        response_language: str | None,
        market_scope: object,
        explicit_languages: list[str] | None,
        explicit_country: str | None,
    ) -> list[tuple[str, tuple[tuple[ProviderName, str | None], ...]]]:
        languages = explicit_languages or plan_search_languages(
            response_language=response_language,
            market_scope=market_scope,
        )
        legs: list[tuple[str, tuple[tuple[ProviderName, str | None], ...]]] = []
        for language in languages:
            providers = _provider_chain_for_language(
                language,
                explicit_country=explicit_country,
            )
            legs.append((language, providers))
        return legs

    async def _collect_provider(
        self,
        *,
        language: str,
        provider: ProviderName,
        country: str | None,
        queries: list[str],
        max_results: int,
        base_kwargs: dict[str, object],
    ) -> tuple[list[CollectorSnippet], dict[str, object], list[str]]:
        channel = {"bocha": self._bocha, "serper": self._serper, "tavily": self._tavily}[provider]
        snippets: list[CollectorSnippet] = []
        metadata: dict[str, object] = {}
        errors: list[str] = []
        for variant in queries:
            leg_args = dict(base_kwargs)
            leg_args.pop("search_languages", None)
            leg_args.pop("language", None)
            leg_args["query"] = variant
            leg_args["max_results"] = max_results
            if provider == "tavily":
                leg_args.pop("country", None)
                leg_args["country"] = country
            elif provider == "serper":
                leg_args.pop("country", None)
                leg_args["country"] = country
                leg_args["language"] = language
            else:
                leg_args.pop("country", None)
            try:
                started_at = time.perf_counter()
                observation = await channel.invoke(**leg_args)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                snippets.extend(observation.result.snippets)
                metadata = {**metadata, **observation.result.metadata}
                log.info(
                    "search_web.provider.ok",
                    provider=provider,
                    language=language,
                    country=country,
                    query_hash=_query_hash(variant),
                    latency_ms=latency_ms,
                    snippet_count=len(observation.result.snippets),
                )
            except (RateLimited, FetchTimeout, ChannelError) as exc:
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                errors.append(f"{variant}:{type(exc).__name__}:{str(exc)[:120]}")
                log.warning(
                    "search_web.provider.fail",
                    provider=provider,
                    language=language,
                    country=country,
                    query_hash=_query_hash(variant),
                    error_class=type(exc).__name__,
                    error_preview=str(exc)[:240],
                    latency_ms=latency_ms,
                    fail_fast=isinstance(exc, (RateLimited, FetchTimeout))
                    or "api_key" in str(exc).lower(),
                )
                if isinstance(exc, (RateLimited, FetchTimeout)) or "api_key" in str(exc).lower():
                    break
                continue
        return _dedupe_snippets(snippets), metadata, errors

    async def _collect_leg(
        self,
        *,
        language: str,
        providers: tuple[tuple[ProviderName, str | None], ...],
        queries: list[str],
        max_results: int,
        base_kwargs: dict[str, object],
    ) -> tuple[list[CollectorSnippet], dict[str, object], list[str], dict[str, int], list[ProviderName]]:
        errors: list[str] = []
        leg_result_counts: dict[str, int] = {}
        if settings.COLLECTOR_SEARCH_BREADTH_ENABLED:
            provider_results = await asyncio.gather(
                *(
                    self._collect_provider(
                        language=language,
                        provider=provider,
                        country=country,
                        queries=queries,
                        max_results=max_results,
                        base_kwargs=base_kwargs,
                    )
                    for provider, country in providers
                )
            )
            merged: list[CollectorSnippet] = []
            merged_metadata: dict[str, object] = {}
            providers_used: list[ProviderName] = []
            for (provider, _country), (snippets, metadata, provider_errors) in zip(
                providers, provider_results
            ):
                leg_result_counts[f"{language}:{provider}"] = len(snippets)
                if snippets:
                    providers_used.append(provider)
                    merged.extend(snippets)
                    merged_metadata = {**merged_metadata, **metadata}
                errors.extend(f"{provider}:{error}" for error in provider_errors)
            return (
                _dedupe_snippets(merged),
                merged_metadata,
                errors,
                leg_result_counts,
                providers_used,
            )

        for provider, country in providers:
            snippets, metadata, provider_errors = await self._collect_provider(
                language=language,
                provider=provider,
                country=country,
                queries=queries,
                max_results=max_results,
                base_kwargs=base_kwargs,
            )
            leg_result_counts[f"{language}:{provider}"] = len(snippets)
            if snippets:
                return snippets, metadata, errors + provider_errors, leg_result_counts, [provider]
            errors.extend(f"{provider}:{error}" for error in provider_errors)
        return [], {}, errors, leg_result_counts, []

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", 5)
        if not isinstance(query, str) or not query.strip():
            raise ChannelError("search_web requires non-empty query.")
        if not isinstance(max_results, int):
            raise ChannelError("search_web max_results must be int.")
        if max_results <= 0 or max_results > 10:
            raise ChannelError("search_web max_results must be in range [1, 10].")

        response_language = _normalize_response_language(kwargs.get("response_language"))
        market_scope = kwargs.get("market_scope")
        country_raw = kwargs.get("country")
        explicit_country = (
            country_raw.strip() if isinstance(country_raw, str) and country_raw.strip() else None
        )
        explicit_languages = _explicit_search_languages(
            kwargs.get("search_languages"), max_languages=_MAX_ROUTER_LANGUAGES
        )
        legs = self._plan_legs(
            response_language=response_language,
            market_scope=market_scope,
            explicit_languages=explicit_languages,
            explicit_country=explicit_country,
        )
        queries = _query_variants(query, kwargs.get("query_variants"))

        # Language fan-out: one leg per target language in parallel (home language first for
        # emphasis). Within each leg, provider breadth merge is feature-flagged so we can
        # quickly revert to first-provider early-return when API quota is constrained.
        collected = await asyncio.gather(
            *(
                self._collect_leg(
                    language=language,
                    providers=providers,
                    queries=queries,
                    max_results=max_results,
                    base_kwargs=kwargs,
                )
                for (language, providers) in legs
            )
        )

        merged: list[CollectorSnippet] = []
        providers_used: list[str] = []
        languages_used: list[str] = []
        leg_result_counts: dict[str, int] = {}
        combined_metadata: dict[str, object] = {}
        errors: list[str] = []
        for (language, _providers), (
            snippets,
            metadata,
            leg_errors,
            provider_counts,
            leg_providers_used,
        ) in zip(legs, collected):
            leg_result_counts.update(provider_counts)
            if snippets:
                languages_used.append(language)
                for provider in leg_providers_used:
                    if provider in providers_used:
                        continue
                    providers_used.append(provider)
                merged.extend(snippets)
                combined_metadata = {**combined_metadata, **metadata}
            if leg_errors:
                errors.append(f"{language}:{' ; '.join(leg_errors)}")

        merged = _dedupe_snippets(merged)
        if not merged:
            log.warning(
                "search_web.all_providers_failed",
                search_languages=[language for (language, _providers) in legs],
                response_language=response_language,
                leg_result_counts=leg_result_counts,
                error_count=len(errors),
                errors_preview=errors[:6],
            )
            raise ChannelError(
                "search_web providers failed: " + (" | ".join(errors) or "no usable snippets")
            )

        search_languages = [language for (language, _providers) in legs]
        breadth_enabled = bool(settings.COLLECTOR_SEARCH_BREADTH_ENABLED)
        log.info(
            "search_web.multilingual",
            search_languages=search_languages,
            languages_used=languages_used,
            providers=providers_used,
            leg_result_counts=leg_result_counts,
            response_language=response_language,
            result_count=len(merged),
            breadth_enabled=breadth_enabled,
        )
        result = ToolObservationResult(
            snippets=merged,
            metadata={
                **combined_metadata,
                "providers": providers_used,
                "search_languages": search_languages,
                "languages_used": languages_used,
                "leg_result_counts": leg_result_counts,
                "response_language": response_language,
                "queries": queries,
                "result_count": len(merged),
                "breadth_enabled": breadth_enabled,
            },
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "query": query,
                "query_variants": queries,
                "max_results": max_results,
                "response_language": response_language,
                "market_scope": market_scope if isinstance(market_scope, str) else None,
                "search_languages": search_languages,
                "providers": providers_used,
                "breadth_enabled": breadth_enabled,
            },
            result=result,
        )
