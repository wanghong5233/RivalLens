from __future__ import annotations

from datetime import datetime, timezone

from agents.nodes.researcher import _build_evidence_rows


def test_build_evidence_rows_strips_null_bytes_from_text_fields() -> None:
    rows, ids = _build_evidence_rows(
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
    row = rows[0]
    assert "\x00" not in row.quote
    assert "\x00" not in row.sanitized_text
    assert row.source_url is not None and "\x00" not in row.source_url
    assert row.source_title is not None and "\x00" not in row.source_title
