from __future__ import annotations

import asyncio
from functools import lru_cache
from urllib.parse import urlsplit

from tavily import TavilyClient
from tavily.errors import (
    BadRequestError as TavilyBadRequestError,
    ForbiddenError as TavilyForbiddenError,
    InvalidAPIKeyError as TavilyInvalidAPIKeyError,
    MissingAPIKeyError as TavilyMissingAPIKeyError,
    TimeoutError as TavilyTimeoutError,
    UsageLimitExceededError as TavilyUsageLimitExceededError,
)

from agents.tools.html_clean import extract_main_text, post_clean_text
from agents.tools.parse_page import infer_source_type, official_hosts_for_competitor
from core.config import settings
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError, FetchTimeout, RateLimited
from service.collector.http_client import get_collector_http_client
from service.collector.rate_limiter import PerHostLimiter
from service.collector.robots import RobotsGate
from service.collector.source_quality import MIN_EXTRACTED_TEXT_CHARS, is_low_semantic_text

_TAVILY_EXTRACT_ERRORS: tuple[type[Exception], ...] = (
    TavilyBadRequestError,
    TavilyForbiddenError,
    TavilyInvalidAPIKeyError,
    TavilyMissingAPIKeyError,
    TavilyTimeoutError,
    TavilyUsageLimitExceededError,
)

# Content types readability cannot parse; we skip the local path so the Tavily
# fallback (or a loud failure) handles them instead of producing garbled text.
_NON_HTML_CONTENT_MARKERS: tuple[str, ...] = (
    "application/pdf",
    "application/zip",
    "application/octet-stream",
    "image/",
    "video/",
    "audio/",
)


@lru_cache
def _get_per_host_limiter() -> PerHostLimiter:
    return PerHostLimiter(qps=settings.COLLECTOR_PER_HOST_QPS)


@lru_cache
def _get_robots_gate() -> RobotsGate:
    return RobotsGate(cache_ttl_seconds=settings.COLLECTOR_ROBOTS_CACHE_TTL_S)


async def _tavily_extract(*, url: str, query: str | None) -> dict[str, object]:
    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    kwargs: dict[str, object] = {
        "urls": [url],
        "extract_depth": "advanced",
        "format": "markdown",
        "include_images": False,
        "timeout": float(settings.COLLECTOR_FETCH_TIMEOUT_S),
    }
    if query:
        kwargs["query"] = query
        kwargs["chunks_per_source"] = 3
    try:
        return await asyncio.to_thread(client.extract, **kwargs)
    except TavilyTimeoutError as exc:
        raise FetchTimeout(f"tavily extract timed out: {exc}") from exc
    except TavilyUsageLimitExceededError as exc:
        raise RateLimited(f"tavily usage limit exceeded: {exc}") from exc
    except _TAVILY_EXTRACT_ERRORS as exc:
        raise ChannelError(f"tavily extract failed ({type(exc).__name__}): {exc}") from exc


def _extract_text_from_tavily_response(response: dict[str, object]) -> tuple[str, str | None]:
    results_raw = response.get("results")
    results = results_raw if isinstance(results_raw, list) else []
    if not results:
        failed_raw = response.get("failed_results")
        raise ChannelError(f"fetch_url extract returned no results; failed_results={failed_raw!r}")
    first = results[0]
    if not isinstance(first, dict):
        raise ChannelError("fetch_url extract returned malformed result.")
    raw_text = first.get("raw_content") or first.get("content")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ChannelError("fetch_url extract returned empty content.")
    source_url_raw = first.get("url")
    source_url = source_url_raw if isinstance(source_url_raw, str) else None
    return raw_text.strip(), source_url


def _validate_extracted_text(text: str) -> None:
    compact = " ".join(text.split())
    low_semantic, reason = is_low_semantic_text(text)
    if not low_semantic:
        return
    if reason == "too_short":
        raise ChannelError(
            f"fetch_url extracted content too short: chars={len(compact)} "
            f"min_chars={MIN_EXTRACTED_TEXT_CHARS}"
        )
    if reason == "navigation_boilerplate":
        raise ChannelError("fetch_url extracted content looks like navigation/footer boilerplate.")
    raise ChannelError(f"fetch_url extracted content is low semantic quality: reason={reason}")


def _looks_like_html(content_type: str | None) -> bool:
    if content_type is None:
        return True
    lowered = content_type.lower()
    return not any(marker in lowered for marker in _NON_HTML_CONTENT_MARKERS)


async def _fetch_via_httpx(*, url: str) -> tuple[str, str]:
    http_client = get_collector_http_client()
    fetched = await http_client.fetch_text(url, retries=1)
    if not _looks_like_html(fetched.content_type):
        raise ChannelError(f"fetch_url httpx got non-HTML content_type={fetched.content_type}")
    extracted_text = extract_main_text(fetched.text)
    _validate_extracted_text(extracted_text)
    return extracted_text, str(fetched.url)


async def _fetch_via_tavily(*, url: str, query: str | None) -> tuple[str, str]:
    if not settings.TAVILY_API_KEY:
        raise ChannelError("TAVILY_API_KEY is required for fetch_url tavily fallback.")
    response = await _tavily_extract(url=url, query=query)
    extracted_text, extracted_url = _extract_text_from_tavily_response(response)
    extracted_text = post_clean_text(extracted_text)
    _validate_extracted_text(extracted_text)
    return extracted_text, extracted_url or url


class FetchUrlChannel(BaseChannel):
    name = "fetch_url"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        url = kwargs.get("url")
        competitor_id = kwargs.get("competitor_id")
        if not isinstance(url, str) or not url.strip():
            raise ChannelError("fetch_url requires non-empty url.")
        if competitor_id is not None and not isinstance(competitor_id, str):
            raise ChannelError("fetch_url competitor_id must be string when provided.")
        query_raw = kwargs.get("query")
        query = query_raw.strip() if isinstance(query_raw, str) and query_raw.strip() else None

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ChannelError(f"fetch_url invalid url={url}")
        host = parsed.netloc.lower()

        http_client = get_collector_http_client()
        await _get_per_host_limiter().acquire(host, timeout_seconds=float(settings.COLLECTOR_FETCH_TIMEOUT_S))
        await _get_robots_gate().ensure_allowed(
            target_url=url,
            user_agent=settings.COLLECTOR_USER_AGENT,
            client=http_client.client,
        )

        # Local httpx extraction is the primary path so collection no longer
        # depends on a paid extract quota; Tavily stays as an optional fallback
        # for pages the local path cannot parse (when a key is configured).
        fetch_source = "httpx_extract"
        try:
            extracted_text, source_url = await _fetch_via_httpx(url=url)
        except (ChannelError, FetchTimeout) as httpx_error:
            try:
                extracted_text, source_url = await _fetch_via_tavily(url=url, query=query)
                fetch_source = "tavily_extract"
            except (ChannelError, FetchTimeout, RateLimited) as tavily_error:
                raise ChannelError(
                    f"fetch_url failed for url={url}: httpx_error={httpx_error}; "
                    f"tavily_error={tavily_error}"
                ) from tavily_error

        source_type = infer_source_type(
            source_url=source_url,
            official_hosts=official_hosts_for_competitor(
                competitor_id if isinstance(competitor_id, str) else None
            ),
        )
        snippet = self._build_snippet(
            raw_text=extracted_text,
            source_type=source_type,
            source_url=source_url,
            source_title=source_url,
            metadata={
                "source": fetch_source,
                "host": host,
                "query": query,
                "competitor_id": competitor_id if isinstance(competitor_id, str) else None,
            },
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "url": url,
                "competitor_id": competitor_id,
                "query": query,
            },
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={
                    "host": host,
                    "source": fetch_source,
                },
            ),
        )
