from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from pydantic import ValidationError

from service.llm import (
    SKILL_CURATOR_SYSTEM_PROMPT,
    build_skill_curator_fallback_user_prompt,
    build_skill_curator_user_prompt,
)
from service.llm.client import get_llm_client
from service.llm.response import LLMResponse
from service.skill_curator.models import SkillCuratorCandidate, SkillCuratorOutput
from utils.logger import get_logger

log = get_logger("service.skill_curator.engine")


@dataclass(slots=True)
class SkillCuratorGenerationResult:
    candidates: list[SkillCuratorCandidate]
    llm_response: LLMResponse
    error: str | None


def _normalize_output(content: dict[str, object]) -> tuple[list[SkillCuratorCandidate], str | None]:
    try:
        parsed = SkillCuratorOutput.model_validate(content)
    except ValidationError as exc:
        return [], f"skill_curator_schema_invalid: {exc.errors()[0]['msg']}"
    return parsed.candidates, None


def _count_candidates(candidates: Sequence[SkillCuratorCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item.candidate_type] = counts.get(item.candidate_type, 0) + 1
    return counts


async def generate_skill_candidates(
    *,
    run_id: str,
    industry_pack: str,
    qa_rejection_count: int,
    qa_reasons: Sequence[str],
    supervisor_decisions: Sequence[dict[str, object]],
    evidence_source_counts: dict[str, int],
    total_evidence_count: int,
) -> SkillCuratorGenerationResult:
    log.info(
        "skill_curator.candidate.start",
        run_id=run_id,
        industry_pack=industry_pack,
        qa_rejection_count=qa_rejection_count,
        total_evidence_count=total_evidence_count,
    )
    llm_response = await get_llm_client().complete_json(
        model_slot="qa",
        system_prompt=SKILL_CURATOR_SYSTEM_PROMPT,
        user_prompt=build_skill_curator_user_prompt(
            run_id=run_id,
            industry_pack=industry_pack,
            qa_rejection_count=qa_rejection_count,
            qa_reasons=qa_reasons,
            supervisor_decisions=supervisor_decisions,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
        fallback_system_prompt=SKILL_CURATOR_SYSTEM_PROMPT,
        fallback_user_prompt=build_skill_curator_fallback_user_prompt(
            run_id=run_id,
            industry_pack=industry_pack,
            qa_rejection_count=qa_rejection_count,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
    )
    if llm_response.error is not None:
        log.info(
            "skill_curator.candidate.finish",
            candidate_count=0,
            candidate_count_by_type={},
            has_error=True,
        )
        return SkillCuratorGenerationResult(
            candidates=[],
            llm_response=llm_response,
            error=llm_response.error,
        )

    candidates, normalize_error = _normalize_output(llm_response.content)
    log.info(
        "skill_curator.candidate.finish",
        candidate_count=len(candidates) if normalize_error is None else 0,
        candidate_count_by_type=_count_candidates(candidates) if normalize_error is None else {},
        has_error=normalize_error is not None,
    )
    return SkillCuratorGenerationResult(
        candidates=candidates,
        llm_response=llm_response,
        error=normalize_error,
    )
