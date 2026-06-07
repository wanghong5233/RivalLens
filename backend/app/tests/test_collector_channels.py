from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.tools.fetch_url import FetchUrlChannel
from agents.tools.parse_page import infer_source_type, official_hosts_for_competitor, source_matches_competitor
from agents.tools.search_web import TavilySearchChannel
from core.config import settings
from service.collector.errors import ChannelError, RobotsBlocked
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
    assert {"search_web", "fetch_url", "extract_structured"}.issubset(
        set(registry.list_actions())
    )


@pytest.mark.asyncio
async def test_search_web_channel_with_mocked_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-tavily-key")
    limiter = _FakeLimiter()
    monkeypatch.setattr("agents.tools.search_web._get_tavily_rate_limiter", lambda: limiter)

    async def _fake_tavily_search(query: str, *, max_results: int) -> dict[str, object]:
        del query, max_results
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
    observation = await channel.invoke(query="cursor pricing", max_results=3)
    assert observation.result.snippets
    assert observation.result.snippets[0].source_type in {"article", "public_review", "pricing_page"}
