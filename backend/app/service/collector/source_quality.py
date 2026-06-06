from __future__ import annotations

import re
from urllib.parse import urlsplit

MIN_EXTRACTED_TEXT_CHARS = 160
NAVIGATION_WORDS = frozenset(
    {
        "home",
        "login",
        "copyright",
        "all rights reserved",
        "privacy policy",
        "terms of service",
        "table of contents",
    }
)
LOW_SEMANTIC_PHRASES = frozenset(
    {
        "welcome back",
        "continue with google",
        "continue with apple",
        "sign in to continue",
        "log in to continue",
        "enable javascript",
        "loading...",
        "please wait",
    }
)
BLOCKED_HOST_SUFFIXES = frozenset(
    {
        "linkedin.com",
        "www.linkedin.com",
    }
)
BLOCKED_PATH_MARKERS = frozenset(
    {
        "/login",
        "/signin",
        "/auth",
        "/checkpoint",
        "/uas/login",
    }
)
WORD_PATTERN = re.compile(r"[A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff0-9_-]*")
SYMBOL_FRAGMENT_PATTERN = re.compile(r"^[\s\-\|:;,_#~`.*=+\\/\[\]{}()<>]+$")


def is_low_semantic_text(
    text: str,
    *,
    min_chars: int = MIN_EXTRACTED_TEXT_CHARS,
) -> tuple[bool, str | None]:
    compact = " ".join(text.split())
    if not compact:
        return True, "empty"
    if len(compact) < min_chars:
        return True, "too_short"
    if SYMBOL_FRAGMENT_PATTERN.fullmatch(compact):
        return True, "symbol_fragment"
    lower = compact.lower()
    if any(phrase in lower for phrase in LOW_SEMANTIC_PHRASES):
        return True, "loading_or_auth_boilerplate"
    navigation_hits = sum(1 for word in NAVIGATION_WORDS if word in lower)
    words = WORD_PATTERN.findall(compact)
    if navigation_hits >= 3 and len(words) < 80:
        return True, "navigation_boilerplate"
    return False, None


def source_blocklist_reason(source_url: str | None) -> str | None:
    if source_url is None:
        return None
    parsed = urlsplit(source_url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not host:
        return None
    if host in BLOCKED_HOST_SUFFIXES or any(host.endswith(f".{suffix}") for suffix in BLOCKED_HOST_SUFFIXES):
        return "blocked_host"
    if any(marker in path for marker in BLOCKED_PATH_MARKERS):
        return "blocked_auth_path"
    return None
