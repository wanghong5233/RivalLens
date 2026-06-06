from __future__ import annotations

from service.llm.prompts import select_layered_evidence_briefs


def test_select_layered_evidence_briefs_covers_competitor_dimension_groups() -> None:
    evidence_briefs: list[dict[str, object]] = []
    for index in range(30):
        evidence_briefs.append(
            {
                "evidence_id": f"old_{index}",
                "competitor_id": "Cursor",
                "dimension": "pricing",
            }
        )
    evidence_briefs.extend(
        [
            {
                "evidence_id": "windsurf_pricing",
                "competitor_id": "Windsurf",
                "dimension": "pricing",
            },
            {
                "evidence_id": "cursor_security",
                "competitor_id": "Cursor",
                "dimension": "security",
            },
            {
                "evidence_id": "windsurf_security",
                "competitor_id": "Windsurf",
                "dimension": "security",
            },
        ]
    )

    selected = select_layered_evidence_briefs(evidence_briefs, limit=4)

    selected_groups = {
        (item.get("competitor_id"), item.get("dimension"))
        for item in selected
    }
    assert len(selected) == 4
    assert selected_groups == {
        ("Cursor", "pricing"),
        ("Windsurf", "pricing"),
        ("Cursor", "security"),
        ("Windsurf", "security"),
    }


def test_select_layered_evidence_briefs_fills_remaining_with_newest() -> None:
    evidence_briefs = [
        {"evidence_id": f"ev_{index}", "competitor_id": "Cursor", "dimension": "pricing"}
        for index in range(10)
    ]

    selected = select_layered_evidence_briefs(evidence_briefs, limit=3)

    assert [item["evidence_id"] for item in selected] == ["ev_7", "ev_8", "ev_9"]
