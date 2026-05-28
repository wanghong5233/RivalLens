from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from service.industry_pack.models import (
    CompetitorSnapshot,
    IndustryPack,
    PackMetadata,
    PromotedQARule,
)
from service.industry_pack.registry import IndustryPackNotFound


def _read_yaml_file(path: Path) -> dict[str, object]:
    if not path.exists():
        raise IndustryPackNotFound(f"Industry pack file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def _read_promoted_qa_rules(path: Path) -> list[PromotedQARule]:
    if not path.exists():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IndustryPackNotFound(f"Failed to parse promoted QA rules YAML: {path}") from exc
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise IndustryPackNotFound(f"Promoted QA rules YAML root must be a list: {path}")
    promoted_rules: list[PromotedQARule] = []
    for index, item in enumerate(loaded):
        if not isinstance(item, dict):
            raise IndustryPackNotFound(
                f"Promoted QA rules entry at index={index} must be an object: {path}"
            )
        try:
            promoted_rules.append(PromotedQARule.model_validate(item))
        except ValidationError as exc:
            raise IndustryPackNotFound(
                f"Invalid promoted QA rule entry at index={index} in {path}: {exc}"
            ) from exc
    return promoted_rules


def load_pack(pack_dir: Path) -> IndustryPack:
    if not pack_dir.exists():
        raise IndustryPackNotFound(f"Industry pack directory does not exist: {pack_dir}")

    metadata_raw = _read_yaml_file(pack_dir / "pack.yaml")
    metadata = PackMetadata.model_validate(metadata_raw)

    competitors: dict[str, CompetitorSnapshot] = {}
    for competitor_file in metadata.competitor_files:
        competitor_path = pack_dir / competitor_file
        competitor_raw = _read_yaml_file(competitor_path)
        competitor = CompetitorSnapshot.model_validate(competitor_raw)
        competitors[competitor.id] = competitor
    promoted_qa_rules = _read_promoted_qa_rules(
        pack_dir / "skills" / "qa_rules_promoted.yaml"
    )

    return IndustryPack(
        id=metadata.id,
        name=metadata.name,
        version=metadata.version,
        default_focus_dimensions=metadata.default_focus_dimensions,
        description=metadata.description,
        competitors=competitors,
        promoted_qa_rules=promoted_qa_rules,
    )
