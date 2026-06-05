from __future__ import annotations

from types import SimpleNamespace

from agents.nodes.discovery import _build_snippet_sample, _filter_discovery_candidates
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


def test_filter_discovery_candidates_keeps_grounded_competitor() -> None:
    quote = "Cursor is an AI code editor used by software teams."
    candidate = SimpleNamespace(
        name="Cursor",
        is_competitor=True,
        relevance_reason="AI coding product in the target market.",
        evidence_quote=quote,
    )

    discovered, filtered_out, relevance = _filter_discovery_candidates(
        candidates=[candidate],
        snippets=[f"Article summary: {quote}"],
    )

    assert discovered == ["Cursor"]
    assert filtered_out == []
    assert relevance == [
        {
            "name": "Cursor",
            "relevance_reason": "AI coding product in the target market.",
            "evidence_quote_preview": quote,
        }
    ]


def test_filter_discovery_candidates_filters_non_competitor() -> None:
    candidate = SimpleNamespace(
        name="TechCrunch",
        is_competitor=False,
        relevance_reason="Publisher, not a direct competitor.",
        evidence_quote="TechCrunch reported on AI coding tools.",
    )

    discovered, filtered_out, relevance = _filter_discovery_candidates(
        candidates=[candidate],
        snippets=["TechCrunch reported on AI coding tools."],
    )

    assert discovered == []
    assert relevance == []
    assert filtered_out == [{"name": "TechCrunch", "reason": "not_competitor"}]


def test_filter_discovery_candidates_dedupes_alias_key() -> None:
    quote = "OpenAI Codex helps developers write code."
    candidates = [
        SimpleNamespace(
            name="OpenAI Codex",
            is_competitor=True,
            relevance_reason="AI coding product.",
            evidence_quote=quote,
        ),
        SimpleNamespace(
            name="OpenAI-Codex",
            is_competitor=True,
            relevance_reason="Duplicate alias.",
            evidence_quote=quote,
        ),
    ]

    discovered, filtered_out, relevance = _filter_discovery_candidates(
        candidates=candidates,
        snippets=[quote],
    )

    assert discovered == ["OpenAI Codex"]
    assert len(relevance) == 1
    assert filtered_out == [{"name": "OpenAI-Codex", "reason": "duplicate_alias"}]


def test_filter_discovery_candidates_filters_grounding_miss() -> None:
    candidate = SimpleNamespace(
        name="Windsurf",
        is_competitor=True,
        relevance_reason="AI coding product.",
        evidence_quote="Windsurf was named as a direct competitor.",
    )

    discovered, filtered_out, relevance = _filter_discovery_candidates(
        candidates=[candidate],
        snippets=["The page only mentions Cursor."],
    )

    assert discovered == []
    assert relevance == []
    assert filtered_out == [{"name": "Windsurf", "reason": "grounding_miss"}]
