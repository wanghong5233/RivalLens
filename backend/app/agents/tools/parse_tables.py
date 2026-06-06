from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from agents.tools.parse_page import infer_source_type
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError


def html_table_to_markdown(table: Tag) -> str:
    rows = table.find_all("tr")
    cells = [
        [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
        for row in rows
    ]
    cells = [row for row in cells if row]
    if not cells:
        return ""
    width = max(len(row) for row in cells)
    normalized = [row + [""] * (width - len(row)) for row in cells]
    header = "| " + " | ".join(normalized[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in normalized[1:])
    if body:
        return "\n".join([header, sep, body])
    return header


def extract_tables_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    blocks: list[str] = []
    for index, table in enumerate(tables, start=1):
        markdown = html_table_to_markdown(table)
        if markdown:
            blocks.append(f"### Table {index}\n\n{markdown}")
    return "\n\n".join(blocks)


class ParseTablesChannel(BaseChannel):
    name = "parse_tables"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        html_raw = kwargs.get("html")
        text_raw = kwargs.get("text")
        source_url = kwargs.get("source_url")
        source_title = kwargs.get("source_title")

        html: str | None = None
        if isinstance(html_raw, str) and html_raw.strip():
            html = html_raw
        elif isinstance(text_raw, str) and "<table" in text_raw.lower():
            html = text_raw

        if html is None:
            raise ChannelError("parse_tables requires html or text containing <table> tags.")

        markdown = extract_tables_markdown(html)
        if not markdown.strip():
            raise ChannelError("parse_tables found no extractable table content.")

        source_type = infer_source_type(
            source_url=source_url if isinstance(source_url, str) else None,
            official_hosts=None,
        )
        snippet = self._build_snippet(
            raw_text=markdown,
            source_type=source_type,
            source_url=source_url if isinstance(source_url, str) else None,
            source_title=(
                source_title if isinstance(source_title, str) else "parsed_tables"
            ),
            metadata={"source": "parse_tables"},
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "source_url": source_url,
                "source_title": source_title,
            },
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={"table_count": markdown.count("### Table")},
            ),
        )
