from __future__ import annotations

from service.knowledge import extract_knowledge_schema


def test_extract_knowledge_schema_populates_triplet_for_comparison() -> None:
    result = extract_knowledge_schema(
        evidence_briefs=[
            {
                "evidence_id": "ev_cursor_feature",
                "competitor_id": "Cursor",
                "dimension": "feature",
                "quote_preview": "Cursor supports repo-aware edits.",
                "source_title": "Cursor Features",
            },
            {
                "evidence_id": "ev_cursor_pricing",
                "competitor_id": "Cursor",
                "dimension": "pricing",
                "quote_preview": "Cursor monthly subscription is published.",
                "source_title": "Cursor Pricing",
            },
            {
                "evidence_id": "ev_cursor_feedback",
                "competitor_id": "Cursor",
                "dimension": "user_feedback",
                "quote_preview": "Teams want faster review cycles.",
                "source_title": "Cursor Reviews",
            },
            {
                "evidence_id": "ev_windsurf_feature",
                "competitor_id": "Windsurf",
                "dimension": "feature",
                "quote_preview": "Windsurf highlights collaborative workflows.",
                "source_title": "Windsurf Features",
            },
            {
                "evidence_id": "ev_windsurf_pricing",
                "competitor_id": "Windsurf",
                "dimension": "pricing_strategy",
                "quote_preview": "Windsurf has annual enterprise bundles.",
                "source_title": "Windsurf Pricing",
            },
            {
                "evidence_id": "ev_windsurf_feedback",
                "competitor_id": "Windsurf",
                "dimension": "user_feedback",
                "quote_preview": "Admins ask for stronger governance controls.",
                "source_title": "Windsurf Reviews",
            },
        ],
        competitors=["Cursor", "Windsurf"],
        focus_dimensions=["feature", "pricing", "user_feedback"],
        analysis_archetype="comparison",
    )

    assert result.extraction_mode == "comparison"
    assert result.schema_version == "schema_v0.2"
    assert len(result.features) >= 2
    assert len(result.pricings) == 2
    assert len(result.personas) == 2
    assert set(result.coverage.keys()) == {"Cursor", "Windsurf"}
    assert result.coverage["Cursor"]["pricing"] == "complete"
    assert result.coverage["Windsurf"]["feedback"] == "partial"
    assert all(item["evidence_ids"] for item in result.features)
    assert all(item["evidence_ids"] for item in result.pricings)
    assert all(item["evidence_ids"] for item in result.personas)


def test_extract_knowledge_schema_filters_invalid_and_unknown_competitors() -> None:
    result = extract_knowledge_schema(
        evidence_briefs=[
            {
                "evidence_id": "",
                "competitor_id": "Cursor",
                "dimension": "feature",
                "quote_preview": "missing evidence id",
                "source_title": "bad row",
            },
            {
                "evidence_id": "ev_unknown_competitor",
                "competitor_id": "UnknownTool",
                "dimension": "feature",
                "quote_preview": "unknown competitor should be filtered",
                "source_title": "unknown",
            },
            {
                "evidence_id": "ev_cursor_pricing",
                "competitor_id": "Cursor",
                "dimension": "pricing",
                "quote_preview": "cursor price",
                "source_title": "Cursor Pricing",
            },
        ],
        competitors=["Cursor"],
        focus_dimensions=["pricing"],
        analysis_archetype="comparison",
    )

    assert result.features == []
    assert len(result.pricings) == 1
    assert result.pricings[0]["competitor_id"] == "Cursor"
    assert result.coverage == {
        "Cursor": {
            "feature": "insufficient_data",
            "pricing": "complete",
            "feedback": "insufficient_data",
        }
    }
    assert result.missing_reasons["Cursor"] == [
        "feature:no_grounded_evidence",
        "persona:no_grounded_evidence",
    ]


def test_extract_knowledge_schema_skips_triplet_in_landscape_mode() -> None:
    result = extract_knowledge_schema(
        evidence_briefs=[
            {
                "evidence_id": "ev_landscape",
                "competitor_id": "DeepSeek",
                "dimension": "monetization_paths",
                "quote_preview": "landscape signal",
                "source_title": "landscape",
            }
        ],
        competitors=["DeepSeek"],
        focus_dimensions=["monetization_paths"],
        analysis_archetype="landscape",
    )

    assert result.extraction_mode == "landscape_skipped"
    assert result.features == []
    assert result.pricings == []
    assert result.personas == []
    assert result.coverage == {
        "DeepSeek": {
            "feature": "insufficient_data",
            "pricing": "insufficient_data",
            "feedback": "insufficient_data",
        }
    }
    assert result.missing_reasons["DeepSeek"] == [
        "landscape:competitor_schema_not_required"
    ]
