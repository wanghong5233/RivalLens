from __future__ import annotations

import asyncio
from functools import lru_cache

from tavily import TavilyClient

from core.config import settings
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError
from service.collector.rate_limiter import PerHostLimiter

from agents.tools.parse_page import infer_source_type


@lru_cache
def _get_tavily_rate_limiter() -> PerHostLimiter:
    return PerHostLimiter(qps=settings.COLLECTOR_PER_HOST_QPS)


async def _tavily_search(query: str, *, max_results: int) -> dict[str, object]:
    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    try:
        return await asyncio.to_thread(
            client.search,
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_raw_content=False,
            include_images=False,
        )
    except TypeError:
        return await asyncio.to_thread(client.search, query=query, max_results=max_results)


class TavilySearchChannel(BaseChannel):
    name = "search_web"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", 5)
        if not isinstance(query, str) or not query.strip():
            raise ChannelError("search_web requires non-empty query.")
        if not isinstance(max_results, int):
            raise ChannelError("search_web max_results must be int.")
        if max_results <= 0 or max_results > 10:
            raise ChannelError("search_web max_results must be in range [1, 10].")
        if not settings.TAVILY_API_KEY:
            raise ChannelError("TAVILY_API_KEY is required for search_web channel.")

        await _get_tavily_rate_limiter().acquire(
            "api.tavily.com",
            timeout_seconds=float(settings.COLLECTOR_FETCH_TIMEOUT_S),
        )
        response = await _tavily_search(query, max_results=max_results)
        results_raw = response.get("results", [])
        results = results_raw if isinstance(results_raw, list) else []
        snippets: list = []
        for result in results:
            if not isinstance(result, dict):
                continue
            raw_text = result.get("content") or result.get("raw_content")
            source_url = result.get("url")
            source_title = result.get("title")
            if not isinstance(raw_text, str) or not raw_text.strip():
                continue
            normalized_url = source_url if isinstance(source_url, str) else None
            normalized_title = source_title if isinstance(source_title, str) else "tavily_result"
            source_type = infer_source_type(source_url=normalized_url, official_hosts=None)
            snippets.append(
                self._build_snippet(
                    raw_text=raw_text,
                    source_type=source_type,
                    source_url=normalized_url,
                    source_title=normalized_title,
                    metadata={
                        "source": "tavily_search",
                        "query": query,
                    },
                )
            )
        if not snippets:
            raise ChannelError("search_web returned no usable snippets.")

        return CollectorObservation(
            channel=self.name,
            args={
                "query": query,
                "max_results": max_results,
            },
            result=ToolObservationResult(
                snippets=snippets,
                metadata={
                    "query": query,
                    "result_count": len(snippets),
                },
            ),
        )
