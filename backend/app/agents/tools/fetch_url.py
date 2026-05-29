from __future__ import annotations

from functools import lru_cache

from core.config import settings
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError
from service.collector.http_client import get_collector_http_client
from service.collector.rate_limiter import PerHostLimiter
from service.collector.robots import RobotsGate
from urllib.parse import urlsplit

from agents.tools.parse_page import extract_main_text, infer_source_type


@lru_cache
def _get_per_host_limiter() -> PerHostLimiter:
    return PerHostLimiter(qps=settings.COLLECTOR_PER_HOST_QPS)


@lru_cache
def _get_robots_gate() -> RobotsGate:
    return RobotsGate(cache_ttl_seconds=settings.COLLECTOR_ROBOTS_CACHE_TTL_S)


class FetchUrlChannel(BaseChannel):
    name = "fetch_url"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        url = kwargs.get("url")
        competitor_id = kwargs.get("competitor_id")
        if not isinstance(url, str) or not url.strip():
            raise ChannelError("fetch_url requires non-empty url.")
        if competitor_id is not None and not isinstance(competitor_id, str):
            raise ChannelError("fetch_url competitor_id must be string when provided.")

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
        fetched = await http_client.fetch_text(url, retries=1)
        extracted_text = extract_main_text(fetched.text)
        source_type = infer_source_type(
            source_url=fetched.url,
            official_hosts=None,
        )
        snippet = self._build_snippet(
            raw_text=extracted_text,
            source_type=source_type,
            source_url=fetched.url,
            source_title=fetched.url,
            metadata={
                "status_code": fetched.status_code,
                "content_type": fetched.content_type or "",
                "source": "fetch_url",
                "host": host,
                "competitor_id": competitor_id if isinstance(competitor_id, str) else None,
            },
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "url": url,
                "competitor_id": competitor_id,
            },
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={
                    "host": host,
                    "status_code": fetched.status_code,
                },
            ),
        )
