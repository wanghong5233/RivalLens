from __future__ import annotations

import pytest

from agents.tools.browser_fetch import needs_browser
from core.config import settings


from service.collector.errors import ChannelError


def test_needs_browser_detects_spa_shell() -> None:
    raw_html = '<html><body><div id="root"></div><script>window.__APP__={}</script></body></html>'
    assert needs_browser("short", raw_html) is True


def test_needs_browser_accepts_rich_static_page() -> None:
    raw_html = "<html><body><main>" + ("Enterprise pricing details. " * 20) + "</main></body></html>"
    extracted = "Enterprise pricing details. " * 20
    assert needs_browser(extracted, raw_html) is False


def test_needs_browser_detects_low_text_ratio() -> None:
    raw_html = "<html><body>" + ("<!-- noise -->" * 500) + "<p>Brief</p></body></html>"
    assert needs_browser("Brief summary only.", raw_html) is True


@pytest.mark.asyncio
async def test_browser_fetch_disabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.tools.browser_fetch import browser_fetch

    monkeypatch.setattr(settings, "COLLECTOR_BROWSER_ENABLED", False)
    with pytest.raises(ChannelError, match="disabled"):
        await browser_fetch("https://example.com", timeout=5)
