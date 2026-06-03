from __future__ import annotations

from agents.subgraphs.researcher import (
    ResearcherSubState,
    _archive_observations_log,
    _build_observation_brief,
    _effective_prompt_size,
    _fallback_fetch_url,
)
from service.llm.prompts import (
    COMPRESSION_PROMPT_CHAR_BUDGET,
    RESEARCH_PROMPT_CHAR_BUDGET,
    build_compression_user_prompt,
    build_researcher_user_prompt,
    evidence_draft_refs_for_prompt,
)


def test_build_researcher_user_prompt_uses_briefs_not_full_observations() -> None:
    huge_quote = "x" * 20_000
    prompt = build_researcher_user_prompt(
        research_topic="topic",
        competitor_id="智简简历",
        focus_dimensions=["pricing"],
        pending_dimensions=["pricing"],
        queried_dimensions=[],
        turn_count=2,
        max_turns=6,
        observation_briefs=[
            {
                "tool": "search_web",
                "dimension": "pricing",
                "snippet_count": 3,
                "quote_preview": huge_quote[:200],
            }
        ],
        compressed_summary="prior summary",
        discovered_urls=["https://example.com/pricing"],
    )
    assert len(prompt) < RESEARCH_PROMPT_CHAR_BUDGET
    assert huge_quote not in prompt
    assert "observation_briefs" in prompt
    assert "discovered_urls" in prompt


def test_compression_prompt_uses_refs_not_full_quotes() -> None:
    huge_quote = "y" * 50_000
    prompt = build_compression_user_prompt(
        messages=[{"role": "user", "content": "hello"}],
        observation_briefs=[{"tool": "search_web", "snippet_count": 1}],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "comp_a",
                "quote": huge_quote,
                "source_url": "https://example.com/pricing",
            }
        ],
        compressed_summary="existing",
    )
    assert len(prompt) < COMPRESSION_PROMPT_CHAR_BUDGET
    assert huge_quote not in prompt
    refs = evidence_draft_refs_for_prompt(
        [{"quote": huge_quote, "dimension": "pricing", "competitor_id": "comp_a"}]
    )
    assert refs[0]["quote_len"] == len(huge_quote)


def test_archive_observations_log_keeps_recent_full_rows() -> None:
    observations = [
        {"tool": "search_web", "args": {"dimension": "pricing"}, "result": {"snippets": [{}]}},
        {"tool": "fetch_url", "args": {"url": "https://a.test"}, "result": {"snippets": [{}, {}]}},
        {"tool": "extract_structured", "args": {}, "result": {"snippets": []}},
    ]
    archived = _archive_observations_log(observations)
    assert archived[0].get("archived") is True
    assert archived[1] == observations[1]
    assert archived[2] == observations[2]


def test_fallback_fetch_url_returns_none_without_real_urls() -> None:
    state: ResearcherSubState = {
        "competitor_id": "智简简历",
        "reference_urls": [],
        "discovered_urls": [],
    }
    assert _fallback_fetch_url(state=state, dimension="pricing") is None


def test_fallback_fetch_url_prefers_discovered_urls() -> None:
    state: ResearcherSubState = {
        "competitor_id": "智简简历",
        "reference_urls": [],
        "discovered_urls": ["https://news.example.com/pricing"],
    }
    assert _fallback_fetch_url(state=state, dimension="pricing") == "https://news.example.com/pricing"


def test_effective_prompt_size_counts_briefs() -> None:
    state: ResearcherSubState = {
        "messages": [{"role": "user", "content": "a" * 100}],
        "observation_briefs": [{"tool": "search_web", "quote_preview": "b" * 500}],
        "evidence_drafts": [{"quote": "c" * 1000, "dimension": "pricing", "competitor_id": "x"}],
        "compressed_summary": "summary",
    }
    size = _effective_prompt_size(state)
    assert size > 600


def test_observation_brief_truncates_error_preview() -> None:
    brief = _build_observation_brief(
        tool="fetch_url",
        args={"url": "https://bad.test"},
        observation_row={"tool": "fetch_url", "error": "e" * 500},
        dimension="pricing",
    )
    preview = brief.get("error_preview")
    assert isinstance(preview, str)
    assert len(preview) <= 200
