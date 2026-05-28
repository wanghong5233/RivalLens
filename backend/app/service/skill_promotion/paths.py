from __future__ import annotations

from pathlib import Path


def build_skills_dir(*, pack_root: Path, pack_id: str) -> Path:
    return pack_root / pack_id / "skills"


def build_qa_rule_path(*, pack_root: Path, pack_id: str) -> Path:
    return build_skills_dir(pack_root=pack_root, pack_id=pack_id) / "qa_rules_promoted.yaml"


def build_source_routing_path(*, pack_root: Path, pack_id: str) -> Path:
    return build_skills_dir(pack_root=pack_root, pack_id=pack_id) / "source_routing.yaml"


def build_prompt_template_path(
    *,
    pack_root: Path,
    pack_id: str,
    template_name: str,
    candidate_id: str,
) -> Path:
    filename = f"{template_name}__{candidate_id}.yaml"
    return (
        build_skills_dir(pack_root=pack_root, pack_id=pack_id)
        / "prompt_templates"
        / filename
    )
