from __future__ import annotations

from datetime import datetime, timezone

from agents.nodes.researcher import _build_evidence_rows, _build_initial_substate
from agents.subgraphs.researcher import _effective_action_dimension
from schemas.supervisor import ConductResearch


def test_build_evidence_rows_strips_null_bytes_from_text_fields() -> None:
    rows, ids, dropped_dimensions = _build_evidence_rows(
        run_id="run_nul_test",
        step_id="step_nul_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["product_market_positioning"],
        evidence_drafts=[
            {
                "dimension": "product_market_positioning",
                "competitor_id": "通义灵码",
                "quote": "官方介绍\x00片段",
                "sanitized_text": "官方介绍\x00片段",
                "source_type": "article",
                "source_url": "https://example.com/\x00page",
                "source_title": "标题\x00测试",
                "desensitized": True,
                "metadata": {},
            }
        ],
        observations_log=[],
        default_competitor_id="通义灵码",
    )
    assert len(rows) == 1
    assert len(ids) == 1
    assert dropped_dimensions == {"count": 0, "reasons": {}}
    row = rows[0]
    assert "\x00" not in row.quote
    assert "\x00" not in row.sanitized_text
    assert row.source_url is not None and "\x00" not in row.source_url
    assert row.source_title is not None and "\x00" not in row.source_title


def test_initial_researcher_substate_raises_turn_budget_to_cover_focus_dimensions() -> None:
    substate = _build_initial_substate(
        run_id="run_turn_budget_test",
        step_id="step_turn_budget_test",
        request=ConductResearch(
            research_topic="Cursor dimensions",
            competitor_id="Cursor",
            focus_dimensions=["core_features", "pricing", "security", "integrations"],
            max_iterations=2,
            fallback_to_offline=True,
        ),
        focus_dimensions=["core_features", "pricing", "security", "integrations"],
        domain_hint=None,
        reference_urls=[],
    )

    assert substate["max_turns"] == 4


def test_build_evidence_rows_keeps_out_of_focus_dimension_as_unclassified() -> None:
    rows, ids, dropped_dimensions = _build_evidence_rows(
        run_id="run_dimension_test",
        step_id="step_dimension_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "dimension": "User Feedback",
                "competitor_id": "Cursor",
                "quote": "Users discuss onboarding friction.",
                "sanitized_text": "Users discuss onboarding friction.",
                "source_type": "article",
                "source_url": "https://example.com/review",
                "source_title": "Review",
                "desensitized": True,
                "metadata": {},
            }
        ],
        observations_log=[],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 1
    assert len(ids) == 1
    assert rows[0].span["dimension"] is None
    assert rows[0].span["dimension_drop_reason"] == "out_of_focus"
    assert dropped_dimensions == {"count": 1, "reasons": {"out_of_focus": 1}}


def test_build_evidence_rows_keeps_missing_dimension_as_unclassified() -> None:
    rows, _, dropped_dimensions = _build_evidence_rows(
        run_id="run_missing_dimension_test",
        step_id="step_missing_dimension_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "competitor_id": "Cursor",
                "quote": "Cursor publishes a public price point.",
                "sanitized_text": "Cursor publishes a public price point.",
                "source_type": "article",
                "source_url": "https://example.com/pricing",
                "source_title": "Pricing",
                "desensitized": True,
                "metadata": {},
            }
        ],
        observations_log=[],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 1
    assert rows[0].span["dimension"] is None
    assert dropped_dimensions == {"count": 1, "reasons": {"missing": 1}}


def test_build_evidence_rows_inherits_dimension_from_observation_args() -> None:
    rows, _, dropped_dimensions = _build_evidence_rows(
        run_id="run_observation_dimension_test",
        step_id="step_observation_dimension_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[],
        observations_log=[
            {
                "tool": "fetch_url",
                "args": {
                    "url": "https://cursor.com/pricing",
                    "competitor_id": "Cursor",
                    "dimension": "pricing",
                },
                "result": {
                    "snippets": [
                        {
                            "quote": "Cursor publishes pricing details for team buyers.",
                            "sanitized_text": "Cursor publishes pricing details for team buyers.",
                            "source_url": "https://cursor.com/pricing",
                            "source_title": "Cursor Pricing",
                            "source_type": "pricing_page",
                            "metadata": {},
                        }
                    ]
                },
            }
        ],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 1
    assert rows[0].span["dimension"] == "pricing"
    assert rows[0].span["competitor_id"] == "Cursor"
    assert dropped_dimensions == {"count": 0, "reasons": {}}


def test_build_evidence_rows_dedupes_draft_and_observation_path() -> None:
    quote = "Cursor publishes pricing details for team buyers."
    rows, _, dropped_dimensions = _build_evidence_rows(
        run_id="run_dedupe_test",
        step_id="step_dedupe_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": quote,
                "sanitized_text": quote,
                "source_type": "pricing_page",
                "source_url": "https://cursor.com/pricing",
                "source_title": "Cursor Pricing",
                "desensitized": True,
                "metadata": {},
            }
        ],
        observations_log=[
            {
                "tool": "fetch_url",
                "args": {"competitor_id": "Cursor", "dimension": "pricing"},
                "result": {
                    "snippets": [
                        {
                            "quote": quote,
                            "sanitized_text": quote,
                            "source_url": "https://cursor.com/pricing",
                            "source_title": "Cursor Pricing",
                            "source_type": "pricing_page",
                            "metadata": {},
                        }
                    ]
                },
            }
        ],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 1
    assert rows[0].quote == quote
    assert dropped_dimensions == {"count": 0, "reasons": {}}


def test_build_evidence_rows_keeps_same_url_for_different_dimensions() -> None:
    rows, _, dropped_dimensions = _build_evidence_rows(
        run_id="run_same_url_dimensions_test",
        step_id="step_same_url_dimensions_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing", "security"],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "Cursor pricing includes a public team plan.",
                "sanitized_text": "Cursor pricing includes a public team plan.",
                "source_type": "pricing_page",
                "source_url": "https://cursor.com/pricing",
                "source_title": "Cursor Pricing",
                "desensitized": True,
                "metadata": {},
            },
            {
                "dimension": "security",
                "competitor_id": "Cursor",
                "quote": "Cursor security controls are described for enterprise buyers.",
                "sanitized_text": "Cursor security controls are described for enterprise buyers.",
                "source_type": "pricing_page",
                "source_url": "https://cursor.com/pricing",
                "source_title": "Cursor Pricing",
                "desensitized": True,
                "metadata": {},
            },
        ],
        observations_log=[],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 2
    assert {row.span["dimension"] for row in rows} == {"pricing", "security"}
    assert dropped_dimensions == {"count": 0, "reasons": {}}


def test_effective_action_dimension_followup_inherits_recent_search() -> None:
    state = {
        "focus_dimensions": ["core_features", "pricing", "security"],
        "pending_dimensions": ["pricing", "security"],
        "observations_log": [
            {"tool": "search_web", "args": {"dimension": "core_features"}},
        ],
    }
    assert (
        _effective_action_dimension(state=state, action_args={}, action="fetch_url")
        == "core_features"
    )
    assert (
        _effective_action_dimension(
            state=state, action_args={}, action="extract_structured"
        )
        == "core_features"
    )


def test_effective_action_dimension_search_uses_pending_head() -> None:
    state = {
        "focus_dimensions": ["core_features", "pricing", "security"],
        "pending_dimensions": ["pricing", "security"],
        "observations_log": [
            {"tool": "search_web", "args": {"dimension": "core_features"}},
        ],
    }
    assert (
        _effective_action_dimension(state=state, action_args={}, action="search_web")
        == "pricing"
    )
