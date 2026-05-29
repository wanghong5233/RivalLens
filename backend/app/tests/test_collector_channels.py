from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.tools.fetch_url import FetchUrlChannel
from agents.tools.parse_page import infer_source_type
from agents.tools.search_web import TavilySearchChannel
from core.config import settings
from service.collector.errors import RobotsBlocked
from service.collector.http_client import CollectorHTTPClient, FetchResponse


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

    observation = await channel.invoke(
        url="https://cursor.com/pricing",
        competitor_id="comp_cursor",
    )
    assert limiter.host == "cursor.com"
    assert limiter.timeout_seconds is not None
    assert observation.result.snippets[0].source_type == "pricing_page"


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
            source_url="https://community.example.com/thread/1",
            official_hosts=None,
        )
        == "public_review"
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
