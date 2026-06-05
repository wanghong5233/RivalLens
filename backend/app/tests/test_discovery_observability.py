from __future__ import annotations

from agents.nodes.discovery import _build_snippet_sample
from service.collector.base import CollectorSnippet


def test_build_snippet_sample_uses_sanitized_preview() -> None:
    snippet = CollectorSnippet(
        quote="raw quote",
        sanitized_text="safe text " * 40,
        source_url="https://example.com/pricing",
        source_title="Example Pricing",
        source_type="pricing_page",
        desensitized=True,
    )

    sample = _build_snippet_sample(snippet=snippet, query="example pricing")

    assert sample is not None
    assert sample["source_title"] == "Example Pricing"
    assert sample["source_url"] == "https://example.com/pricing"
    assert sample["source_type"] == "pricing_page"
    assert sample["query"] == "example pricing"
    quote_preview = sample["quote_preview"]
    assert isinstance(quote_preview, str)
    assert quote_preview.startswith("safe text")
    assert len(quote_preview) == 220
