from __future__ import annotations

from pathlib import Path

import pytest

from agents.tools.pack_lookup import ToolError, pack_lookup
from core.config import settings
from service.industry_pack.registry import get_industry_pack_registry


def _load_default_pack() -> None:
    registry = get_industry_pack_registry()
    packs_dir = Path(settings.INDUSTRY_PACKS_DIR)
    if not packs_dir.exists():
        packs_dir = Path("/app/industry_packs")
    registry.load_all(packs_dir)


def test_pack_lookup_success() -> None:
    _load_default_pack()
    observation = pack_lookup(
        industry_pack_id="ai_coding_tools",
        competitor_id="comp_cursor",
        dimension="feature",
    )

    assert observation.tool == "pack_lookup"
    assert observation.result["competitor_id"] == "comp_cursor"
    snippets = observation.result["snippets"]
    assert isinstance(snippets, list)
    assert len(snippets) >= 1
    assert "source_url" in snippets[0]


def test_pack_lookup_missing_competitor_raises() -> None:
    _load_default_pack()
    with pytest.raises(ToolError):
        pack_lookup(
            industry_pack_id="ai_coding_tools",
            competitor_id="comp_not_exist",
            dimension="feature",
        )


def test_pack_lookup_missing_dimension_snippet_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_default_pack()

    registry = get_industry_pack_registry()
    pack = registry.get("ai_coding_tools")
    competitor = pack.competitors["comp_cursor"]
    monkeypatch.setitem(competitor.snapshots, "feature", [])

    with pytest.raises(ToolError):
        pack_lookup(
            industry_pack_id="ai_coding_tools",
            competitor_id="comp_cursor",
            dimension="feature",
        )
