from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agents.nodes.researcher import _build_evidence_rows, _build_initial_substate, researcher_node
from agents.subgraphs.researcher import _append_evidence_drafts, _effective_action_dimension
from models.step import Step
from service.event_bus import RunEventType
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
        market_scope="中国市场",
        response_language="zh",
        reference_urls=[],
    )

    assert substate["max_turns"] == 4
    assert substate["market_scope"] == "中国市场"
    assert substate["response_language"] == "zh"


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


def test_append_evidence_drafts_keeps_same_url_for_different_dimensions() -> None:
    drafts = _append_evidence_drafts(
        evidence_drafts=[],
        observation={
            "competitor_id": "Cursor",
            "snippets": [
                {
                    "quote": "Cursor pricing includes a public team plan.",
                    "sanitized_text": "Cursor pricing includes a public team plan.",
                    "source_url": "https://cursor.com/pricing",
                    "source_title": "Cursor Pricing",
                    "source_type": "pricing_page",
                    "metadata": {"dimension": "pricing"},
                },
                {
                    "quote": "Cursor security controls are described for enterprise buyers.",
                    "sanitized_text": "Cursor security controls are described for enterprise buyers.",
                    "source_url": "https://cursor.com/pricing",
                    "source_title": "Cursor Pricing",
                    "source_type": "pricing_page",
                    "metadata": {"dimension": "security"},
                },
            ],
        },
        focus_dimensions=["pricing", "security"],
    )

    assert len(drafts) == 2
    assert {draft["dimension"] for draft in drafts} == {"pricing", "security"}


def test_append_evidence_drafts_dedupes_same_identity_only() -> None:
    drafts = _append_evidence_drafts(
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "Cursor pricing includes a public team plan.",
                "source_url": "https://cursor.com/pricing",
            }
        ],
        observation={
            "competitor_id": "Cursor",
            "dimension": "pricing",
            "snippets": [
                {
                    "quote": "Cursor pricing includes a public team plan.",
                    "sanitized_text": "Cursor pricing includes a public team plan.",
                    "source_url": "https://cursor.com/pricing",
                    "source_title": "Cursor Pricing",
                    "source_type": "pricing_page",
                    "metadata": {},
                },
                {
                    "quote": "Cursor pricing also documents enterprise billing controls.",
                    "sanitized_text": "Cursor pricing also documents enterprise billing controls.",
                    "source_url": "https://cursor.com/pricing",
                    "source_title": "Cursor Pricing",
                    "source_type": "pricing_page",
                    "metadata": {},
                },
            ],
        },
        focus_dimensions=["pricing"],
    )

    assert len(drafts) == 2
    assert drafts[1]["quote"] == "Cursor pricing also documents enterprise billing controls."


def test_build_evidence_rows_applies_source_quality_gate() -> None:
    rows, _, dropped_dimensions = _build_evidence_rows(
        run_id="run_source_quality_test",
        step_id="step_source_quality_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "Welcome back. Continue with Google. Sign in to continue.",
                "sanitized_text": "Welcome back. Continue with Google. Sign in to continue.",
                "source_type": "article",
                "source_url": "https://example.com/login",
                "source_title": "Login",
                "desensitized": True,
                "metadata": {},
            },
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "--- | --- | ---",
                "sanitized_text": "--- | --- | ---",
                "source_type": "article",
                "source_url": "https://example.com/table",
                "source_title": "Table",
                "desensitized": True,
                "metadata": {},
            },
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "LinkedIn login wall content for a competitor page.",
                "sanitized_text": "LinkedIn login wall content for a competitor page.",
                "source_type": "article",
                "source_url": "https://www.linkedin.com/login",
                "source_title": "LinkedIn",
                "desensitized": True,
                "metadata": {},
            },
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "Cursor publishes paid team plan details and enterprise controls for buyers.",
                "sanitized_text": "Cursor publishes paid team plan details and enterprise controls for buyers.",
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

    assert len(rows) == 1
    assert rows[0].source_url == "https://cursor.com/pricing"
    assert dropped_dimensions["reasons"]["source_blocklist"] == 2
    assert dropped_dimensions["reasons"]["low_semantic"] == 1


def test_build_evidence_rows_marks_source_authority_and_competitor_match() -> None:
    rows, _, dropped_dimensions = _build_evidence_rows(
        run_id="run_source_authority_test",
        step_id="step_source_authority_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "Cursor pricing page describes team plans for buyers.",
                "sanitized_text": "Cursor pricing page describes team plans for buyers.",
                "source_type": "article",
                "source_url": "https://cursor.com/pricing",
                "source_title": "Cursor Pricing",
                "desensitized": True,
                "metadata": {},
            },
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "BillingPlatform discusses general pricing automation for B2B vendors.",
                "sanitized_text": "BillingPlatform discusses general pricing automation for B2B vendors.",
                "source_type": "pricing_page",
                "source_url": "https://billingplatform.com/pricing",
                "source_title": "BillingPlatform Pricing",
                "desensitized": True,
                "metadata": {},
            },
        ],
        observations_log=[],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 2
    official_row = next(row for row in rows if row.source_url == "https://cursor.com/pricing")
    mismatch_row = next(row for row in rows if row.source_url == "https://billingplatform.com/pricing")
    assert official_row.source_type == "pricing_page"
    assert official_row.span["source_authority"] == "official"
    assert official_row.span["competitor_source_match"] is True
    assert mismatch_row.span["source_authority"] == "third_party"
    assert mismatch_row.span["competitor_source_match"] is False
    assert dropped_dimensions == {"count": 0, "reasons": {}}


def test_build_evidence_rows_downgrades_cross_vendor_official_source_type() -> None:
    rows, _, _ = _build_evidence_rows(
        run_id="run_cross_vendor_test",
        step_id="step_cross_vendor_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "A GitHub docs page that upstream tools labeled official by host union.",
                "sanitized_text": "A GitHub docs page that upstream tools labeled official by host union.",
                "source_type": "official_site",
                "source_url": "https://github.com/features/copilot",
                "source_title": "GitHub Copilot",
                "desensitized": True,
                "metadata": {},
            },
        ],
        observations_log=[],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.source_type == "article"
    assert row.span["competitor_source_match"] is False
    assert row.span["source_authority"] == "third_party"


def test_build_evidence_rows_restores_quality_floor_when_gate_filters_all_candidates() -> None:
    rows, ids, dropped_dimensions = _build_evidence_rows(
        run_id="run_source_quality_floor_test",
        step_id="step_source_quality_floor_test",
        collected_at=datetime.now(timezone.utc),
        focus_dimensions=["pricing"],
        evidence_drafts=[
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "Welcome back. Continue with Google. Sign in to continue.",
                "sanitized_text": "Welcome back. Continue with Google. Sign in to continue.",
                "source_type": "article",
                "source_url": "https://example.com/login",
                "source_title": "Login",
                "desensitized": True,
                "metadata": {},
            },
            {
                "dimension": "pricing",
                "competitor_id": "Cursor",
                "quote": "--- | --- | ---",
                "sanitized_text": "--- | --- | ---",
                "source_type": "article",
                "source_url": "https://example.com/table",
                "source_title": "Table",
                "desensitized": True,
                "metadata": {},
            },
        ],
        observations_log=[],
        default_competitor_id="Cursor",
    )

    assert len(rows) == 1
    assert len(ids) == 1
    assert rows[0].span["source_quality_floor"] is True
    assert rows[0].span["source_quality_drop_reason"] == "source_blocklist"
    assert dropped_dimensions["reasons"] == {"source_blocklist": 1, "low_semantic": 1}


@pytest.mark.asyncio
async def test_researcher_node_degrades_zero_evidence_without_requeue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    added_rows: list[object] = []
    captured_events: list[tuple[RunEventType, str | None, dict[str, object]]] = []

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        def add(self, row: object) -> None:
            added_rows.append(row)

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _FakeSubgraph:
        async def ainvoke(self, _: object) -> dict[str, object]:
            return {
                "evidence_drafts": [],
                "observations_log": [],
                "llm_calls": [],
                "turn_count": 1,
                "compression_count": 0,
                "queried_dimensions": ["pricing"],
                "final_summary": "No grounded evidence found.",
            }

    async def _fake_emit_run_event(
        *,
        run_id: str,
        event_type: RunEventType,
        step_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        del run_id
        captured_events.append((event_type, step_id, dict(payload or {})))

    monkeypatch.setattr("agents.nodes.researcher.get_session_factory", lambda: _FakeSession)
    monkeypatch.setattr("agents.nodes.researcher.get_researcher_subgraph", lambda: _FakeSubgraph())
    monkeypatch.setattr("agents.nodes.researcher.emit_run_event", _fake_emit_run_event)

    result = await researcher_node(
        {
            "run_id": "run_zero_evidence",
            "pending_tool_args": {
                "research_topic": "Cursor pricing",
                "competitor_id": "Cursor",
                "focus_dimensions": ["pricing"],
                "max_iterations": 1,
                "fallback_to_offline": True,
            },
            "researched_competitors": [],
        }
    )

    step_rows = [row for row in added_rows if isinstance(row, Step)]
    assert len(step_rows) == 1
    step = step_rows[0]
    assert step.status == "degraded"
    assert step.payload["uncovered"] is True
    assert step.payload["degraded_reason"] == "researcher_zero_evidence"
    assert step.payload["evidence_ids"] == []
    assert result["researched_competitors"] == ["Cursor"]
    assert result["researcher_degraded_competitors"] == ["Cursor"]
    assert captured_events[-1][0] == RunEventType.STEP_FINISH
    assert captured_events[-1][2]["status"] == "degraded"
    assert captured_events[-1][2]["evidence_count"] == 0


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
