from __future__ import annotations

import io
from urllib.parse import urlsplit

import pdfplumber

from agents.tools.parse_page import infer_source_type
from agents.tools.parse_tables import html_table_to_markdown
from bs4 import BeautifulSoup, Tag
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError
from service.collector.http_client import get_collector_http_client


def _table_rows_to_markdown(rows: list[list[str | None]]) -> str:
    if not rows:
        return ""
    normalized = [
        [cell or "" for cell in row]
        for row in rows
        if any(cell for cell in row)
    ]
    if not normalized:
        return ""
    width = max(len(row) for row in normalized)
    padded = [row + [""] * (width - len(row)) for row in normalized]
    header = "| " + " | ".join(padded[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in padded[1:])
    if body:
        return "\n".join([header, sep, body])
    return header


def _extract_pdf(raw_bytes: bytes) -> str:
    texts: list[str] = []
    tables_md: list[str] = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if isinstance(page_text, str) and page_text.strip():
                texts.append(page_text.strip())
            for table in page.extract_tables() or []:
                markdown = _table_rows_to_markdown(table)
                if markdown:
                    tables_md.append(markdown)
    body = "\n\n".join(texts)
    if tables_md:
        body = f"{body}\n\n" + "\n\n".join(tables_md) if body else "\n\n".join(tables_md)
    return body.strip()


def _extract_html_document(raw_bytes: bytes) -> str:
    html = raw_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    tables_md: list[str] = []
    for index, table in enumerate(soup.find_all("table"), start=1):
        if isinstance(table, Tag):
            markdown = html_table_to_markdown(table)
            if markdown:
                tables_md.append(f"### Table {index}\n\n{markdown}")
    text = soup.get_text(separator="\n", strip=True)
    if tables_md:
        return f"{text}\n\n" + "\n\n".join(tables_md) if text else "\n\n".join(tables_md)
    return text


def _resolve_document_extractor(content_type: str | None, url: str) -> str:
    lowered_type = (content_type or "").lower()
    lowered_url = url.lower()
    if "pdf" in lowered_type or lowered_url.endswith(".pdf"):
        return "pdf"
    if "html" in lowered_type or lowered_url.endswith((".html", ".htm")):
        return "html"
    return "unknown"


class ParseDocumentChannel(BaseChannel):
    name = "parse_document"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        url = kwargs.get("url")
        source_title = kwargs.get("source_title")
        if not isinstance(url, str) or not url.strip():
            raise ChannelError("parse_document requires non-empty url.")

        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ChannelError(f"parse_document invalid url={url}")

        http_client = get_collector_http_client()
        fetched = await http_client.fetch_bytes(url.strip(), retries=1)
        doc_kind = _resolve_document_extractor(fetched.content_type, url.strip())
        if doc_kind == "pdf":
            extracted = _extract_pdf(fetched.raw_bytes)
        elif doc_kind == "html":
            extracted = _extract_html_document(fetched.raw_bytes)
        else:
            raise ChannelError(
                f"parse_document unsupported content_type={fetched.content_type!r} url={url}"
            )
        if not extracted.strip():
            raise ChannelError("parse_document extracted empty content.")

        source_type = infer_source_type(source_url=fetched.url, official_hosts=None)
        snippet = self._build_snippet(
            raw_text=extracted,
            source_type=source_type,
            source_url=fetched.url,
            source_title=source_title if isinstance(source_title, str) else fetched.url,
            metadata={"source": "parse_document", "doc_kind": doc_kind},
        )
        return CollectorObservation(
            channel=self.name,
            args={"url": url, "source_title": source_title},
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={"doc_kind": doc_kind},
            ),
        )
