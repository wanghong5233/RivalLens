from __future__ import annotations

import re
from urllib.parse import urlsplit

MIN_EXTRACTED_TEXT_CHARS = 160
NAVIGATION_WORDS = frozenset(
    {
        "coding",
        "home",
        "login",
        "sign in",
        "tools",
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
        "sign in home",
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
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*]\([^)]*\)")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+]\([^)]*\)")


def _markdown_image_dominant(compact: str) -> bool:
    image_matches = MARKDOWN_IMAGE_PATTERN.findall(compact)
    if not image_matches:
        return False
    image_chars = sum(len(item) for item in image_matches)
    words = WORD_PATTERN.findall(MARKDOWN_IMAGE_PATTERN.sub(" ", compact))
    return image_chars / max(len(compact), 1) >= 0.25 and len(words) < 40


def _link_density_high(compact: str) -> bool:
    link_chars = sum(len(item) for item in MARKDOWN_LINK_PATTERN.findall(compact))
    if link_chars == 0:
        return False
    return link_chars / max(len(compact), 1) >= 0.35


def _looks_like_navigation_directory(*, lower: str, compact: str, words: list[str]) -> bool:
    prefix = lower[:160]
    starts_with_nav = (
        prefix.startswith("sign in ")
        or prefix.startswith("home ")
        or "sign in home" in prefix
        or "home tools coding" in prefix
        or "home/tools/coding" in prefix
    )
    directory_markers = (
        "tools/coding" in prefix
        or "tools coding" in prefix
        or "alternatives" in prefix
        or "reviews" in prefix
    )
    navigation_hits = sum(1 for word in NAVIGATION_WORDS if word in lower)
    prefix_navigation_hits = sum(1 for word in NAVIGATION_WORDS if word in prefix)
    return (
        starts_with_nav
        and directory_markers
        and navigation_hits >= 3
        and (_link_density_high(compact) or prefix_navigation_hits >= 3 or len(words) < 180)
    )


def is_low_semantic_text(
    text: str,
    *,
    min_chars: int = MIN_EXTRACTED_TEXT_CHARS,
) -> tuple[bool, str | None]:
    compact = " ".join(text.split())
    if not compact:
        return True, "empty"
    if SYMBOL_FRAGMENT_PATTERN.fullmatch(compact):
        return True, "symbol_fragment"
    if _markdown_image_dominant(compact):
        return True, "image_markdown"
    if len(compact) < min_chars:
        return True, "too_short"
    lower = compact.lower()
    navigation_hits = sum(1 for word in NAVIGATION_WORDS if word in lower)
    words = WORD_PATTERN.findall(compact)
    if _looks_like_navigation_directory(lower=lower, compact=compact, words=words):
        return True, "navigation_directory"
    if navigation_hits >= 3 and len(words) < 80:
        return True, "navigation_boilerplate"
    if any(phrase in lower for phrase in LOW_SEMANTIC_PHRASES):
        return True, "loading_or_auth_boilerplate"
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
