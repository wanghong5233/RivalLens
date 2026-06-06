from __future__ import annotations

from urllib.parse import urlsplit

from service.collector.base import SourceType


REVIEW_HOST_KEYWORDS = ("forum", "reddit", "community", "review", "discuss", "news.ycombinator")
DOC_PATH_KEYWORDS = ("/docs", "/api", "/reference")
PRICING_PATH_KEYWORDS = ("/pricing", "/plans")


def infer_source_type(
    *,
    source_url: str | None,
    official_hosts: set[str] | None = None,
) -> SourceType:
    if not source_url:
        return "article"
    parsed = urlsplit(source_url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if official_hosts and host in official_hosts:
        if any(keyword in path for keyword in DOC_PATH_KEYWORDS):
            return "docs"
        if any(keyword in path for keyword in PRICING_PATH_KEYWORDS):
            return "pricing_page"
        return "official_site"
    if any(keyword in host for keyword in REVIEW_HOST_KEYWORDS):
        return "public_review"
    if any(keyword in path for keyword in PRICING_PATH_KEYWORDS):
        return "pricing_page"
    return "article"
