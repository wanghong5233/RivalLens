from __future__ import annotations

import asyncio
import re
import shutil
from functools import lru_cache

from core.config import settings
from service.collector.errors import ChannelError

_SPA_MARKERS = re.compile(
    r"__NEXT_DATA__|__NUXT__|window\.__APP__|<div id=\"app\"></div>"
    r"|<div id=\"root\"></div>|ng-version=|data-reactroot",
    re.IGNORECASE,
)


def needs_browser(extracted_text: str, raw_html: str) -> bool:
    if len(extracted_text) < 150:
        return True
    ratio = len(extracted_text) / max(len(raw_html), 1)
    if ratio < 0.05:
        return True
    if _SPA_MARKERS.search(raw_html[:8000]):
        return True
    return False


@lru_cache
def _get_browser_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(max(1, settings.COLLECTOR_BROWSER_MAX_CONCURRENT))


async def browser_fetch(url: str, *, timeout: int) -> str:
    if not settings.COLLECTOR_BROWSER_ENABLED:
        raise ChannelError("browser fetch disabled by COLLECTOR_BROWSER_ENABLED=false.")
    browser_bin = settings.COLLECTOR_AGENT_BROWSER_BIN.strip()
    if not browser_bin or shutil.which(browser_bin) is None:
        raise ChannelError(f"{browser_bin or 'agent-browser'} CLI is not installed.")

    async with _get_browser_semaphore():
        open_proc = await asyncio.create_subprocess_exec(
            browser_bin,
            "open",
            url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(open_proc.wait(), timeout=timeout)
        except TimeoutError as exc:
            open_proc.kill()
            raise ChannelError(f"browser_fetch open timed out url={url}") from exc

        snap_proc = await asyncio.create_subprocess_exec(
            browser_bin,
            "snapshot",
            "-i",
            "-c",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(snap_proc.communicate(), timeout=timeout)
        except TimeoutError as exc:
            snap_proc.kill()
            raise ChannelError(f"browser_fetch snapshot timed out url={url}") from exc

    text = stdout.decode("utf-8", errors="replace").strip()
    if not text:
        raise ChannelError("browser_fetch snapshot returned empty content.")
    return text
