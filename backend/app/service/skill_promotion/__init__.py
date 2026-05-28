from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from models.skill_candidate import SkillCandidateRecord
from schemas.skill import (
    PromptTemplateCandidatePayload,
    QARuleCandidatePayload,
    SourceRoutingCandidatePayload,
)
from service.skill_promotion.paths import (
    build_prompt_template_path,
    build_qa_rule_path,
    build_source_routing_path,
)
from service.skill_promotion.types import PromotedArtifact
from service.skill_promotion.writers import (
    PromotionWriteError,
    append_qa_rule_entry,
    append_source_routing_entry,
    write_prompt_template_entry,
)


def _entry_meta(
    *,
    record: SkillCandidateRecord,
    reviewed_by: str,
    reviewed_at: datetime,
) -> dict[str, object]:
    return {
        "candidate_id": record.id,
        "approved_by": reviewed_by,
        "approved_at": reviewed_at.isoformat(),
        "supporting_run_ids": list(record.supporting_run_ids),
    }


def _as_dict(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise PromotionWriteError("Skill candidate payload must be an object.")
    return payload


def _build_qa_rule_entry(
    *,
    record: SkillCandidateRecord,
    reviewed_by: str,
    reviewed_at: datetime,
) -> dict[str, object]:
    payload = QARuleCandidatePayload.model_validate(_as_dict(record.payload))
    rule_yaml = payload.rule_yaml
    rule_id = f"promoted_{record.id}"
    for line in rule_yaml.splitlines():
        stripped = line.strip()
        if stripped.startswith("id:"):
            rule_id_candidate = stripped[3:].strip()
            if rule_id_candidate:
                rule_id = rule_id_candidate
            break
    return {
        "rule_id": rule_id,
        "rule_yaml": payload.rule_yaml,
        **_entry_meta(record=record, reviewed_by=reviewed_by, reviewed_at=reviewed_at),
    }


def _build_prompt_template_entry(
    *,
    record: SkillCandidateRecord,
    reviewed_by: str,
    reviewed_at: datetime,
) -> tuple[str, dict[str, object]]:
    payload = PromptTemplateCandidatePayload.model_validate(_as_dict(record.payload))
    entry = {
        "target_agent": payload.target_agent,
        "template_name": payload.template_name,
        "template_body": payload.template_body,
        "replaces_template_id": payload.replaces_template_id,
        "evidence_quality_delta": payload.evidence_quality_delta,
        "rejection_rate_delta": payload.rejection_rate_delta,
        **_entry_meta(record=record, reviewed_by=reviewed_by, reviewed_at=reviewed_at),
    }
    return payload.template_name, entry


def _build_source_routing_entry(
    *,
    record: SkillCandidateRecord,
    reviewed_by: str,
    reviewed_at: datetime,
) -> dict[str, object]:
    payload = SourceRoutingCandidatePayload.model_validate(_as_dict(record.payload))
    return {
        "source_type": payload.source_type,
        "competitor_category": payload.competitor_category,
        "priority_delta": payload.priority_delta,
        "quality_score_sample": list(payload.quality_score_sample),
        **_entry_meta(record=record, reviewed_by=reviewed_by, reviewed_at=reviewed_at),
    }


def promote_approved_candidate(
    *,
    record: SkillCandidateRecord,
    pack_root: Path,
    reviewed_by: str,
    reviewed_at: datetime,
) -> list[PromotedArtifact]:
    artifacts: list[PromotedArtifact] = []
    try:
        if record.candidate_type == "qa_rule":
            entry = _build_qa_rule_entry(
                record=record,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
            )
            path = build_qa_rule_path(
                pack_root=pack_root,
                pack_id=record.industry_pack,
            )
            action = append_qa_rule_entry(path=path, entry=entry)
            artifacts.append(
                {
                    "path": str(path),
                    "action": action,  # type: ignore[typeddict-item]
                    "entry_id": str(entry["rule_id"]),
                }
            )
            return artifacts

        if record.candidate_type == "prompt_template":
            template_name, entry = _build_prompt_template_entry(
                record=record,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
            )
            path = build_prompt_template_path(
                pack_root=pack_root,
                pack_id=record.industry_pack,
                template_name=template_name,
                candidate_id=record.id,
            )
            action = write_prompt_template_entry(path=path, entry=entry)
            artifacts.append(
                {
                    "path": str(path),
                    "action": action,  # type: ignore[typeddict-item]
                    "entry_id": record.id,
                }
            )
            return artifacts

        if record.candidate_type == "source_routing":
            entry = _build_source_routing_entry(
                record=record,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
            )
            path = build_source_routing_path(
                pack_root=pack_root,
                pack_id=record.industry_pack,
            )
            action = append_source_routing_entry(path=path, entry=entry)
            artifacts.append(
                {
                    "path": str(path),
                    "action": action,  # type: ignore[typeddict-item]
                    "entry_id": record.id,
                }
            )
            return artifacts

        raise PromotionWriteError(
            f"Unsupported skill candidate type: {record.candidate_type}"
        )
    except ValidationError as exc:
        raise PromotionWriteError(
            f"Invalid skill candidate payload for {record.candidate_type}: {exc}"
        ) from exc


__all__ = ["PromotedArtifact", "PromotionWriteError", "promote_approved_candidate"]
