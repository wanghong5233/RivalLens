from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.tools.fetch_url import FetchUrlChannel
from agents.tools.parse_page import infer_source_type, official_hosts_for_competitor, source_matches_competitor
from agents.tools.rerank_bocha import _request_bocha_rerank, rerank
from agents.tools.search_bocha import BochaSearchChannel
from agents.tools.search_router import SearchWebRouterChannel
from agents.tools.search_web import TavilySearchChannel
from core.config import settings
from service.collector.base import CollectorObservation, CollectorSnippet, ToolObservationResult
from service.collector.errors import ChannelError, RateLimited, RobotsBlocked
from service.collector.http_client import CollectorHTTPClient, FetchResponse
from service.collector.registry import ChannelRegistry, _register_builtin_channels


@dataclass
class _FakeLimiter:
    host: str | None = None
    timeout_seconds: float | None = None

    async def acquire(self, host: str, *, timeout_seconds: float | None = None) -> None:
        self.host = host
        self.timeout_seconds = timeout_seconds


class _AllowRobotsGate:
    async def ensure_allowed(self, *, target_url: str, user_agent: str, client: object) -> None:
        del target_url, user_agent, client


class _BlockRobotsGate:
    async def ensure_allowed(self, *, target_url: str, user_agent: str, client: object) -> None:
        del user_agent, client
        raise RobotsBlocked(f"blocked by robots: {target_url}")


@dataclass
class _FakeHTTPClient:
    fetch_response: FetchResponse

    @property
    def client(self) -> object:
        return object()

    async def fetch_text(self, url: str, *, retries: int = 1) -> FetchResponse:
        del retries
        return FetchResponse(
            url=url,
            status_code=self.fetch_response.status_code,
            text=self.fetch_response.text,
            content_type=self.fetch_response.content_type,
        )


class _FakeBochaResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = "ok"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeBochaAsyncClient:
    def __init__(self, response: _FakeBochaResponse) -> None:
        self.response = response
        self.post_kwargs: dict[str, object] | None = None

    async def __aenter__(self) -> "_FakeBochaAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb

    async def post(self, url: str, **kwargs: object) -> _FakeBochaResponse:
        self.post_kwargs = {"url": url, **kwargs}
        return self.response


class _FakeSearchChannel:
    def __init__(
        self,
        *,
        provider: str,
        source_url: str = "https://example.com/result",
        exc: Exception | None = None,
    ) -> None:
        self.provider = provider
        self.source_url = source_url
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        self.calls.append(dict(kwargs))
        if self.exc is not None:
            raise self.exc
        query = kwargs.get("query")
        return CollectorObservation(
            channel=f"{self.provider}_search",
            args=dict(kwargs),
            result=ToolObservationResult(
                snippets=[
                    CollectorSnippet(
                        quote=f"{self.provider} result for {query}",
                        sanitized_text=f"{self.provider} result for {query}",
                        source_url=self.source_url,
                        source_title=f"{self.provider} title",
                        source_type="article",
                        desensitized=True,
                        metadata={"source": f"{self.provider}_search"},
                    )
                ],
                metadata={"provider": self.provider},
            ),
        )


@pytest.mark.asyncio
async def test_fetch_url_channel_respects_robots_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = FetchUrlChannel()
    limiter = _FakeLimiter()
    monkeypatch.setattr("agents.tools.fetch_url._get_per_host_limiter", lambda: limiter)
    monkeypatch.setattr("agents.tools.fetch_url._get_robots_gate", lambda: _BlockRobotsGate())
    monkeypatch.setattr(
        "agents.tools.fetch_url.get_collector_http_client",
        lambda: _FakeHTTPClient(
            FetchResponse(
                url="https://example.com",
                status_code=200,
                text="<html><body>ok</body></html>",
                content_type="text/html",
            )
        ),
    )

    with pytest.raises(RobotsBlocked):
        await channel.invoke(url="https://example.com/docs/a")


@pytest.mark.asyncio
async def test_fetch_url_channel_records_host_for_qps(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = FetchUrlChannel()
    limiter = _FakeLimiter()
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setattr("agents.tools.fetch_url._get_per_host_limiter", lambda: limiter)
    monkeypatch.setattr("agents.tools.fetch_url._get_robots_gate", lambda: _AllowRobotsGate())
    monkeypatch.setattr(
        "agents.tools.fetch_url.get_collector_http_client",
        lambda: _FakeHTTPClient(
            FetchResponse(
                url="https://cursor.com/pricing",
                status_code=200,
                text="<html><body>Pricing page content</body></html>",
                content_type="text/html",
            )
        ),
    )
    async def _fake_tavily_extract(*, url: str, query: str | None) -> dict[str, object]:
        del query
        return {
            "results": [
                {
                    "url": url,
                    "raw_content": (
                        "Cursor pricing page content with enough substance for extraction. "
                        "It describes enterprise plans, usage limits, admin controls, privacy, "
                        "security, and billing details for team buyers in multiple paragraphs."
                    ),
                }
            ]
        }

    monkeypatch.setattr("agents.tools.fetch_url._tavily_extract", _fake_tavily_extract)

    observation = await channel.invoke(
        url="https://cursor.com/pricing",
        competitor_id="comp_cursor",
    )
    assert limiter.host == "cursor.com"
    assert limiter.timeout_seconds is not None
    assert observation.result.snippets[0].source_type == "pricing_page"
    assert observation.result.snippets[0].metadata["source"] == "tavily_extract"


@pytest.mark.asyncio
async def test_fetch_url_channel_rejects_low_quality_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = FetchUrlChannel()
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setattr("agents.tools.fetch_url._get_per_host_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr("agents.tools.fetch_url._get_robots_gate", lambda: _AllowRobotsGate())
    monkeypatch.setattr(
        "agents.tools.fetch_url.get_collector_http_client",
        lambda: _FakeHTTPClient(
            FetchResponse(
                url="https://example.com",
                status_code=200,
                text="unused",
                content_type="text/html",
            )
        ),
    )

    async def _fake_tavily_extract(*, url: str, query: str | None) -> dict[str, object]:
        del url, query
        return {"results": [{"url": "https://example.com", "raw_content": "Copyright All rights reserved"}]}

    monkeypatch.setattr("agents.tools.fetch_url._tavily_extract", _fake_tavily_extract)

    with pytest.raises(ChannelError, match="too short"):
        await channel.invoke(url="https://example.com")


def test_collector_http_client_sets_user_agent_header() -> None:
    client = CollectorHTTPClient(user_agent="RivalLens-Researcher/0.1 test", timeout_seconds=3)
    assert client.client.headers.get("User-Agent") == "RivalLens-Researcher/0.1 test"


def test_source_type_mapping_rules() -> None:
    assert (
        infer_source_type(
            source_url="https://cursor.com/docs/api",
            official_hosts={"cursor.com"},
        )
        == "docs"
    )
    assert (
        infer_source_type(
            source_url="https://cursor.com/pricing",
            official_hosts={"cursor.com"},
        )
        == "pricing_page"
    )
    assert (
        infer_source_type(
            source_url="https://www.cursor.com/pricing",
            official_hosts=official_hosts_for_competitor("Cursor"),
        )
        == "pricing_page"
    )
    assert source_matches_competitor(
        source_url="https://cursor.com/pricing",
        competitor_id="Cursor",
    ) is True
    assert source_matches_competitor(
        source_url="https://billingplatform.com/blog/pricing",
        competitor_id="Cursor",
    ) is False
    assert (
        infer_source_type(
            source_url="https://community.example.com/thread/1",
            official_hosts=None,
        )
        == "public_review"
    )


def test_official_hosts_heuristic_for_dynamic_competitor() -> None:
    openai_hosts = official_hosts_for_competitor("OpenAI")
    assert "openai.com" in openai_hosts
    assert (
        infer_source_type(
            source_url="https://openai.com/docs/guides",
            official_hosts=openai_hosts,
        )
        == "docs"
    )
    assert source_matches_competitor(
        source_url="https://openai.com/pricing",
        competitor_id="OpenAI",
    ) is True
    # An unrelated vendor domain must not be treated as this competitor's official source.
    assert source_matches_competitor(
        source_url="https://github.com/features",
        competitor_id="OpenAI",
    ) is False
    assert (
        infer_source_type(
            source_url="https://github.com/features",
            official_hosts=official_hosts_for_competitor("OpenAI"),
        )
        == "article"
    )


def test_tongyi_lingma_aliyun_help_is_official_docs() -> None:
    official_hosts = official_hosts_for_competitor("通义灵码")
    assert "help.aliyun.com" in official_hosts
    assert (
        infer_source_type(
            source_url="https://help.aliyun.com/zh/lingma/product-overview",
            official_hosts=official_hosts,
        )
        == "docs"
    )
    assert source_matches_competitor(
        source_url="https://help.aliyun.com/zh/lingma/product-overview",
        competitor_id="通义灵码",
    ) is True
    assert source_matches_competitor(
        source_url="https://developer.aliyun.com/article/1662698",
        competitor_id="通义灵码",
    ) is False
    assert (
        infer_source_type(
            source_url="https://developer.aliyun.com/article/1662698",
            official_hosts=official_hosts,
        )
        == "article"
    )


def test_builtin_registry_no_longer_registers_parse_page() -> None:
    registry = ChannelRegistry()
    _register_builtin_channels(registry)
    assert "parse_page" not in registry.list_actions()
    assert {"search_web", "bocha_search", "fetch_url", "extract_structured"}.issubset(
        set(registry.list_actions())
    )


@pytest.mark.asyncio
async def test_bocha_search_channel_with_mocked_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", "test-bocha-key")
    monkeypatch.setattr(settings, "BOCHA_BASE_URL", "https://api.bochaai.com/v1")
    limiter = _FakeLimiter()
    monkeypatch.setattr("agents.tools.search_bocha._get_bocha_rate_limiter", lambda: limiter)
    response = _FakeBochaResponse(
        {
            "code": 200,
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "销售 AI 工具评测",
                            "url": "https://example.cn/sales-ai",
                            "summary": "国内销售团队正在评估 AI 跟进工具。",
                            "snippet": "fallback snippet",
                            "siteName": "Example CN",
                            "datePublished": "2026-06-01",
                        }
                    ]
                }
            },
        }
    )
    fake_client = _FakeBochaAsyncClient(response)
    monkeypatch.setattr("agents.tools.search_bocha.httpx.AsyncClient", lambda **_: fake_client)

    observation = await BochaSearchChannel().invoke(query="销售 AI 工具", max_results=3)

    assert limiter.host == "api.bochaai.com"
    assert fake_client.post_kwargs is not None
    assert fake_client.post_kwargs["url"] == "https://api.bochaai.com/v1/web-search"
    assert observation.result.metadata["provider"] == "bocha"
    assert observation.result.snippets[0].sanitized_text == "国内销售团队正在评估 AI 跟进工具。"
    assert observation.result.snippets[0].metadata["source"] == "bocha_search"


@pytest.mark.asyncio
async def test_bocha_search_channel_classifies_body_quota_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", "test-bocha-key")
    monkeypatch.setattr("agents.tools.search_bocha._get_bocha_rate_limiter", lambda: _FakeLimiter())
    fake_client = _FakeBochaAsyncClient(_FakeBochaResponse({"code": 403, "message": "quota"}))
    monkeypatch.setattr("agents.tools.search_bocha.httpx.AsyncClient", lambda **_: fake_client)

    with pytest.raises(RateLimited):
        await BochaSearchChannel().invoke(query="销售 AI 工具", max_results=3)


@pytest.mark.asyncio
async def test_bocha_search_channel_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", None)

    with pytest.raises(ChannelError, match="BOCHA_API_KEY"):
        await BochaSearchChannel().invoke(query="销售 AI 工具", max_results=3)


@pytest.mark.asyncio
async def test_bocha_rerank_with_mocked_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", "test-bocha-key")
    monkeypatch.setattr(settings, "BOCHA_BASE_URL", "https://api.bochaai.com/v1")
    monkeypatch.setattr(settings, "BOCHA_RERANK_MODEL", "gte-rerank")
    limiter = _FakeLimiter()
    monkeypatch.setattr("agents.tools.rerank_bocha._get_bocha_rerank_rate_limiter", lambda: limiter)
    response = _FakeBochaResponse(
        {
            "code": 200,
            "data": {
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.34},
                ]
            },
        }
    )
    fake_client = _FakeBochaAsyncClient(response)
    monkeypatch.setattr("agents.tools.rerank_bocha.httpx.AsyncClient", lambda **_: fake_client)

    ranked = await _request_bocha_rerank(
        query="销售 AI 工具",
        documents=["弱相关", "强相关"],
        top_n=2,
    )

    assert limiter.host == "api.bochaai.com"
    assert fake_client.post_kwargs is not None
    assert fake_client.post_kwargs["url"] == "https://api.bochaai.com/v1/rerank"
    assert ranked == [(1, 0.91), (0, 0.34)]


@pytest.mark.asyncio
async def test_bocha_rerank_preserves_zero_relevance_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", "test-bocha-key")
    monkeypatch.setattr(settings, "BOCHA_BASE_URL", "https://api.bochaai.com/v1")
    monkeypatch.setattr("agents.tools.rerank_bocha._get_bocha_rerank_rate_limiter", lambda: _FakeLimiter())
    fake_client = _FakeBochaAsyncClient(
        _FakeBochaResponse(
            {
                "code": 200,
                "data": {
                    "results": [
                        {"index": 0, "relevance_score": 0},
                        {"index": 1, "score": 0.42},
                    ]
                },
            }
        )
    )
    monkeypatch.setattr("agents.tools.rerank_bocha.httpx.AsyncClient", lambda **_: fake_client)

    ranked = await _request_bocha_rerank(
        query="销售 AI 工具",
        documents=["无关", "相关"],
        top_n=2,
    )

    assert ranked == [(0, 0.0), (1, 0.42)]


@pytest.mark.asyncio
async def test_bocha_rerank_classifies_body_quota_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", "test-bocha-key")
    monkeypatch.setattr("agents.tools.rerank_bocha._get_bocha_rerank_rate_limiter", lambda: _FakeLimiter())
    fake_client = _FakeBochaAsyncClient(_FakeBochaResponse({"code": 403, "message": "quota"}))
    monkeypatch.setattr("agents.tools.rerank_bocha.httpx.AsyncClient", lambda **_: fake_client)

    with pytest.raises(RateLimited):
        await _request_bocha_rerank(
            query="销售 AI 工具",
            documents=["a", "b"],
            top_n=2,
        )


@pytest.mark.asyncio
async def test_bocha_rerank_fail_soft_returns_original_order_when_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", None)

    ranked = await rerank(
        query="销售 AI 工具",
        documents=["a", "b"],
        top_n=2,
    )

    assert ranked == [(0, None), (1, None)]


@pytest.mark.asyncio
async def test_search_router_queries_both_providers_with_chinese_emphasis() -> None:
    bocha = _FakeSearchChannel(provider="bocha", source_url="https://example.cn/a")
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.com/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="销售 AI 工具",
        max_results=3,
        response_language="zh",
        market_scope="中国市场",
    )

    assert observation.channel == "search_web"
    # Breadth: home language (zh→bocha) + global (en→tavily), never excluded by language.
    assert observation.args["providers"] == ["bocha", "tavily"]
    assert observation.args["search_languages"] == ["zh", "en"]
    assert len(bocha.calls) == 1
    assert len(tavily.calls) == 1
    # Emphasis: home (bocha) results lead after merge.
    assert len(observation.result.snippets) == 2
    assert observation.result.snippets[0].source_url == "https://example.cn/a"


@pytest.mark.asyncio
async def test_search_router_degrades_to_tavily_when_bocha_fails() -> None:
    bocha = _FakeSearchChannel(provider="bocha", exc=RateLimited("quota"))
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.com/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="销售 AI 工具",
        max_results=3,
        response_language="zh",
        market_scope="中国市场",
    )

    assert observation.args["providers"] == ["tavily"]
    assert observation.args["search_languages"] == ["zh", "en"]
    assert len(bocha.calls) == 1
    assert len(tavily.calls) == 2
    assert {call.get("country") for call in tavily.calls} == {"china", None}


@pytest.mark.asyncio
async def test_search_router_falls_back_to_tavily_china_for_explicit_zh_when_bocha_key_missing() -> None:
    bocha = _FakeSearchChannel(
        provider="bocha",
        exc=ChannelError("BOCHA_API_KEY is required for bocha_search channel."),
    )
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.cn/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="销售 AI 工具",
        max_results=3,
        search_languages=["zh"],
    )

    assert observation.args["providers"] == ["tavily"]
    assert observation.args["search_languages"] == ["zh"]
    assert len(bocha.calls) == 1
    assert len(tavily.calls) == 1
    assert tavily.calls[0]["country"] == "china"
    assert observation.result.metadata["leg_result_counts"] == {
        "zh:bocha": 0,
        "zh:tavily": 1,
    }


@pytest.mark.asyncio
async def test_search_router_runs_query_variants_and_dedupes_across_providers() -> None:
    bocha = _FakeSearchChannel(provider="bocha", source_url="https://example.cn/a?utm=1")
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.cn/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="销售 AI 工具",
        query_variants=["销售 AI 工具", "销售 AI 工具 评测"],
        max_results=3,
        response_language="zh",
    )

    assert [call["query"] for call in bocha.calls] == ["销售 AI 工具", "销售 AI 工具 评测"]
    assert [call["query"] for call in tavily.calls] == ["销售 AI 工具", "销售 AI 工具 评测"]
    # Same canonical URL from both providers collapses to one; home (bocha) copy is kept.
    assert len(observation.result.snippets) == 1
    assert observation.result.snippets[0].source_url == "https://example.cn/a?utm=1"
    assert observation.result.metadata["queries"] == ["销售 AI 工具", "销售 AI 工具 评测"]


@pytest.mark.asyncio
async def test_search_router_adds_market_language_leg_for_japan_scope() -> None:
    # Highlight: an English run about the Japan market also retrieves Japanese-locale sources.
    bocha = _FakeSearchChannel(provider="bocha", source_url="https://example.cn/a")
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.com/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="best manga creation tools",
        max_results=3,
        response_language="en",
        market_scope="日本市场",
    )

    assert observation.args["search_languages"] == ["en", "ja"]
    assert bocha.calls == []
    countries = sorted(str(call.get("country")) for call in tavily.calls)
    assert countries == ["None", "japan"]


@pytest.mark.asyncio
async def test_search_router_english_user_china_market_adds_chinese_leg() -> None:
    # Highlight: market language is added regardless of output language — an English user
    # analyzing the China market still searches native Chinese sources via Bocha.
    bocha = _FakeSearchChannel(provider="bocha", source_url="https://example.cn/a")
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.com/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="cloud IDE competitors",
        max_results=3,
        response_language="en",
        market_scope="中国大陆市场",
    )

    assert observation.args["search_languages"] == ["en", "zh"]
    # en is home (leads); zh is added from market scope. Both engines are queried.
    assert observation.args["providers"] == ["tavily", "bocha"]
    assert len(bocha.calls) == 1
    assert len(tavily.calls) == 1


@pytest.mark.asyncio
async def test_search_router_honors_explicit_niche_languages() -> None:
    # Highlight: niche languages are reachable by passing search_languages explicitly.
    bocha = _FakeSearchChannel(provider="bocha", source_url="https://example.cn/a")
    tavily = _FakeSearchChannel(provider="tavily", source_url="https://example.com/a")
    channel = SearchWebRouterChannel(bocha_channel=bocha, tavily_channel=tavily)

    observation = await channel.invoke(
        query="industrial automation vendors",
        max_results=3,
        response_language="en",
        search_languages=["ko", "de"],
    )

    assert observation.args["search_languages"] == ["ko", "de"]
    assert bocha.calls == []
    countries = sorted(str(call.get("country")) for call in tavily.calls)
    assert countries == ["germany", "south korea"]


@pytest.mark.asyncio
async def test_search_web_channel_with_mocked_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-tavily-key")
    limiter = _FakeLimiter()
    monkeypatch.setattr("agents.tools.search_web._get_tavily_rate_limiter", lambda: limiter)

    async def _fake_tavily_search(
        query: str,
        *,
        max_results: int,
        country: str | None = None,
    ) -> dict[str, object]:
        del query, max_results
        assert country == "china"
        return {
            "results": [
                {
                    "title": "Cursor pricing update",
                    "url": "https://news.example.com/cursor-pricing",
                    "content": "Cursor updated pricing tiers in public release notes.",
                }
            ]
        }

    monkeypatch.setattr("agents.tools.search_web._tavily_search", _fake_tavily_search)
    channel = TavilySearchChannel()
    observation = await channel.invoke(query="cursor pricing", max_results=3, country="china")
    assert observation.result.snippets
    assert observation.args["country"] == "china"
    assert observation.result.snippets[0].source_type in {"article", "public_review", "pricing_page"}
