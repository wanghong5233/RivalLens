from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import settings
from service.industry_pack.loader import load_pack
from service.industry_pack.registry import IndustryPackNotFound, IndustryPackRegistry


def test_load_pack_happy_path() -> None:
    pack_dir = Path(settings.INDUSTRY_PACKS_DIR) / "ai_coding_tools"
    pack = load_pack(pack_dir)
    assert pack.id == "ai_coding_tools"
    assert "comp_cursor" in pack.competitors
    assert "comp_windsurf" in pack.competitors
    assert "feature" in pack.default_focus_dimensions


def test_load_pack_missing_directory_raises() -> None:
    with pytest.raises(IndustryPackNotFound):
        load_pack(Path("/tmp/pack_does_not_exist"))


def test_load_pack_invalid_dimension_raises_validation_error(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack_invalid_dimension"
    competitors_dir = pack_dir / "competitors"
    competitors_dir.mkdir(parents=True)
    (pack_dir / "pack.yaml").write_text(
        "\n".join(
            [
                "id: invalid_pack",
                "name: Invalid Pack",
                'version: "0.1"',
                "default_focus_dimensions:",
                "  - feature",
                'description: "invalid test pack"',
                "competitor_files:",
                "  - competitors/bad.yaml",
            ]
        ),
        encoding="utf-8",
    )
    (competitors_dir / "bad.yaml").write_text(
        "\n".join(
            [
                "id: comp_bad",
                "display_name: Bad Competitor",
                "aliases: [bad]",
                "official_url: https://example.com",
                "category: ide_assistant",
                "snapshots:",
                "  invalid_dim:",
                '    - quote: "bad dimension"',
                "      source_url: https://example.com/source",
                '      source_title: "bad source"',
                "      desensitized: true",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_pack(pack_dir)


def test_registry_get_missing_pack_raises() -> None:
    registry = IndustryPackRegistry()
    with pytest.raises(IndustryPackNotFound):
        registry.get("not_exists")


def test_load_pack_reads_promoted_qa_rules(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack_with_promoted_rules"
    competitors_dir = pack_dir / "competitors"
    skills_dir = pack_dir / "skills"
    competitors_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    (pack_dir / "pack.yaml").write_text(
        "\n".join(
            [
                "id: promoted_pack",
                "name: Promoted Pack",
                'version: "0.1"',
                "default_focus_dimensions:",
                "  - feature",
                'description: "pack with promoted rules"',
                "competitor_files:",
                "  - competitors/base.yaml",
            ]
        ),
        encoding="utf-8",
    )
    (competitors_dir / "base.yaml").write_text(
        "\n".join(
            [
                "id: comp_base",
                "display_name: Base Competitor",
                "aliases: [base]",
                "official_url: https://example.com",
                "category: ide_assistant",
                "snapshots: {}",
            ]
        ),
        encoding="utf-8",
    )
    (skills_dir / "qa_rules_promoted.yaml").write_text(
        "\n".join(
            [
                "- rule_id: rule_promoted_feature_signal",
                '  rule_yaml: "id: rule_promoted_feature_signal"',
                "  candidate_id: skill_123",
                "  approved_by: owner_wh",
                "  approved_at: '2026-05-27T12:00:00+00:00'",
                "  supporting_run_ids:",
                "    - run_123",
            ]
        ),
        encoding="utf-8",
    )
    pack = load_pack(pack_dir)
    assert len(pack.promoted_qa_rules) == 1
    assert pack.promoted_qa_rules[0].rule_id == "rule_promoted_feature_signal"


def test_load_pack_invalid_promoted_qa_rules_raises(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack_invalid_promoted_rules"
    competitors_dir = pack_dir / "competitors"
    skills_dir = pack_dir / "skills"
    competitors_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    (pack_dir / "pack.yaml").write_text(
        "\n".join(
            [
                "id: invalid_promoted_pack",
                "name: Invalid Promoted Pack",
                'version: "0.1"',
                "default_focus_dimensions:",
                "  - feature",
                'description: "pack with invalid promoted rules"',
                "competitor_files:",
                "  - competitors/base.yaml",
            ]
        ),
        encoding="utf-8",
    )
    (competitors_dir / "base.yaml").write_text(
        "\n".join(
            [
                "id: comp_base",
                "display_name: Base Competitor",
                "aliases: [base]",
                "official_url: https://example.com",
                "category: ide_assistant",
                "snapshots: {}",
            ]
        ),
        encoding="utf-8",
    )
    (skills_dir / "qa_rules_promoted.yaml").write_text(
        "invalid_root: object",
        encoding="utf-8",
    )
    with pytest.raises(IndustryPackNotFound):
        load_pack(pack_dir)
