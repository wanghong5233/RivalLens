from __future__ import annotations

from pathlib import Path

import yaml

from service.industry_pack.models import CompetitorSnapshot, IndustryPack, PackMetadata
from service.industry_pack.registry import IndustryPackNotFound


def _read_yaml_file(path: Path) -> dict[str, object]:
    if not path.exists():
        raise IndustryPackNotFound(f"Industry pack file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


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

    return IndustryPack(
        id=metadata.id,
        name=metadata.name,
        version=metadata.version,
        default_focus_dimensions=metadata.default_focus_dimensions,
        description=metadata.description,
        competitors=competitors,
    )
