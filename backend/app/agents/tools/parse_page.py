from __future__ import annotations

from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from readability import Document

from service.collector.base import BaseChannel, CollectorObservation, SourceType, ToolObservationResult
from service.collector.errors import ChannelError


REVIEW_HOST_KEYWORDS = ("forum", "reddit", "community", "review", "discuss", "news.ycombinator")
DOC_PATH_KEYWORDS = ("/docs", "/api", "/reference")
PRICING_PATH_KEYWORDS = ("/pricing", "/plans")


def extract_main_text(html: str) -> str:
    doc = Document(html)
    summary_html = doc.summary(html_partial=True)
    summary_soup = BeautifulSoup(summary_html, "lxml")
    summary_text = summary_soup.get_text(separator="\n", strip=True)
    if summary_text:
        return summary_text
    soup = BeautifulSoup(html, "lxml")
    fallback_text = soup.get_text(separator="\n", strip=True)
    if fallback_text:
        return fallback_text
    raise ChannelError("parse_page extracted empty text.")


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


class ParsePageChannel(BaseChannel):
    name = "parse_page"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        html = kwargs.get("html")
        source_url = kwargs.get("source_url")
        source_title = kwargs.get("source_title")
        if not isinstance(html, str) or not html.strip():
            raise ChannelError("parse_page requires non-empty html.")
        if source_url is not None and not isinstance(source_url, str):
            raise ChannelError("parse_page source_url must be string when provided.")
        if source_title is not None and not isinstance(source_title, str):
            raise ChannelError("parse_page source_title must be string when provided.")

        extracted_text = extract_main_text(html)
        source_type = infer_source_type(source_url=source_url, official_hosts=None)
        snippet = self._build_snippet(
            raw_text=extracted_text,
            source_type=source_type,
            source_url=source_url,
            source_title=source_title,
            metadata={
                "source": "parse_page",
            },
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "source_url": source_url,
                "source_title": source_title,
            },
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={"source_url": source_url},
            ),
        )
