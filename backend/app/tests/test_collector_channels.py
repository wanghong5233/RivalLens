from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.tools.fetch_url import FetchUrlChannel
from agents.tools.parse_document import ParseDocumentChannel
from agents.tools.parse_images import ParseImagesChannel
from agents.tools.parse_page import infer_source_type
from agents.tools.search_web import TavilySearchChannel
from core.config import settings
from schemas.agent_outputs import ParseImagesOutput
from service.collector.errors import ChannelError, RobotsBlocked
from service.collector.http_client import CollectorHTTPClient, FetchBytesResponse, FetchResponse
from service.collector.registry import ChannelRegistry, _register_builtin_channels
from service.llm.harness import StructuredLLMResult
from service.llm.response import LLMResponse


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
    fetch_bytes_response: FetchBytesResponse | None = None

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

    async def fetch_bytes(self, url: str, *, retries: int = 1) -> FetchBytesResponse:
        del retries
        if self.fetch_bytes_response is None:
            raise ChannelError("fetch_bytes not configured in test fake client.")
        return FetchBytesResponse(
            url=url,
            status_code=self.fetch_bytes_response.status_code,
            raw_bytes=self.fetch_bytes_response.raw_bytes,
            content_type=self.fetch_bytes_response.content_type,
        )


_RICH_PRICING_HTML = """
<html><body><main>
<h1>Cursor Pricing</h1>
<p>Enterprise and team plans with advanced admin controls, privacy settings,
security controls, billing options, usage limits, and dedicated support for
large engineering organizations evaluating AI coding assistants.</p>
<p>Pro tier includes unlimited completions, priority access, and extended context
windows for professional developers building production applications.</p>
</main></body></html>
"""


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
                text=_RICH_PRICING_HTML,
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
    assert observation.result.snippets[0].metadata["source"] == "httpx_extract"


@pytest.mark.asyncio
async def test_fetch_url_channel_rejects_low_quality_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = FetchUrlChannel()
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setattr(settings, "COLLECTOR_BROWSER_ENABLED", False)
    monkeypatch.setattr("agents.tools.fetch_url._get_per_host_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr("agents.tools.fetch_url._get_robots_gate", lambda: _AllowRobotsGate())
    monkeypatch.setattr(
        "agents.tools.fetch_url.get_collector_http_client",
        lambda: _FakeHTTPClient(
            FetchResponse(
                url="https://example.com",
                status_code=200,
                text='<html><body><div id="root"></div></body></html>',
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
            source_url="https://community.example.com/thread/1",
            official_hosts=None,
        )
        == "public_review"
    )


def test_builtin_registry_registers_collector_channels() -> None:
    registry = ChannelRegistry()
    _register_builtin_channels(registry)
    actions = set(registry.list_actions())
    assert {"parse_tables", "parse_images", "parse_document"}.issubset(actions)
    assert {"search_web", "fetch_url", "extract_structured"}.issubset(actions)


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


@pytest.mark.asyncio
async def test_parse_images_channel_uses_vision_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_complete_structured(**kwargs: object) -> StructuredLLMResult[ParseImagesOutput]:
        del kwargs
        return StructuredLLMResult(
            value=ParseImagesOutput(description="Pro plan $99/mo with team admin controls."),
            outcome="primary",
            llm_response=LLMResponse(
                model_slot="vision",
                provider="doubao",
                model_name="ep-vision",
                prompt_preview="preview",
                prompt_hash="abc",
                content={"description": "Pro plan $99/mo with team admin controls."},
                prompt_tokens=1,
                completion_tokens=1,
                latency_ms=10,
                error=None,
            ),
            validation_errors=(),
            attempts=(),
        )

    monkeypatch.setattr("agents.tools.parse_images.complete_structured", _fake_complete_structured)
    channel = ParseImagesChannel()
    observation = await channel.invoke(
        image_urls=["https://cdn.example.com/pricing.png"],
        source_url="https://cursor.com/pricing",
        source_title="Cursor pricing screenshot",
    )
    assert observation.result.snippets[0].metadata["source"] == "parse_images"
    assert "$99" in observation.result.snippets[0].quote


@pytest.mark.asyncio
async def test_parse_document_channel_extracts_html_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html_bytes = (
        b"<html><body><main><h1>Security Whitepaper</h1>"
        b"<p>Enterprise customers receive SOC2 reports, SSO, and audit logs "
        b"for compliance reviews across regulated industries and global teams.</p>"
        b"<table><tr><th>Control</th><th>Status</th></tr>"
        b"<tr><td>SSO</td><td>Enabled</td></tr></table>"
        b"</main></body></html>"
    )
    monkeypatch.setattr(
        "agents.tools.parse_document.get_collector_http_client",
        lambda: _FakeHTTPClient(
            fetch_response=FetchResponse(
                url="https://example.com/security.html",
                status_code=200,
                text="unused",
                content_type="text/html",
            ),
            fetch_bytes_response=FetchBytesResponse(
                url="https://example.com/security.html",
                status_code=200,
                raw_bytes=html_bytes,
                content_type="text/html",
            ),
        ),
    )
    channel = ParseDocumentChannel()
    observation = await channel.invoke(url="https://example.com/security.html")
    assert observation.result.snippets[0].metadata["source"] == "parse_document"
    assert "SOC2" in observation.result.snippets[0].quote
    assert observation.result.metadata["doc_kind"] == "html"
