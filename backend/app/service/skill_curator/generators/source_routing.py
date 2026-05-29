from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from pydantic import ValidationError

from service.llm.client import get_llm_client
from service.llm.response import LLMResponse
from service.skill_curator.generators.tags import infer_candidate_tags
from service.skill_curator.models import SkillCuratorCandidate, SkillCuratorOutput
from service.skill_curator.prompts import (
    SKILL_CURATOR_SOURCE_ROUTING_SYSTEM_PROMPT,
    build_skill_curator_source_routing_fallback_user_prompt,
    build_skill_curator_source_routing_user_prompt,
)
from utils.logger import get_logger

log = get_logger("service.skill_curator.generator.source_routing")


@dataclass(slots=True)
class CuratorGeneratorResult:
    candidates: list[SkillCuratorCandidate]
    llm_response: LLMResponse
    error: str | None


def _normalize_output(content: dict[str, object]) -> tuple[list[SkillCuratorCandidate], str | None]:
    try:
        parsed = SkillCuratorOutput.model_validate(content)
    except ValidationError as exc:
        return [], f"skill_curator_schema_invalid: {exc.errors()[0]['msg']}"
    filtered = [item for item in parsed.candidates if item.candidate_type == "source_routing"]
    return filtered, None


async def generate_source_routing_candidates(
    *,
    run_id: str,
    domain_hint: str | None,
    qa_rejection_count: int,
    qa_reasons: Sequence[str],
    supervisor_decisions: Sequence[dict[str, object]],
    evidence_source_counts: dict[str, int],
    total_evidence_count: int,
) -> CuratorGeneratorResult:
    inferred_tags = infer_candidate_tags(
        domain_hint=domain_hint,
        evidence_source_counts=evidence_source_counts,
        qa_rejection_count=qa_rejection_count,
    )
    log.info(
        "skill_curator.source_routing.start",
        run_id=run_id,
        domain_hint=domain_hint,
        inferred_tags=inferred_tags,
    )
    llm_response = await get_llm_client().complete_json(
        model_slot="qa",
        system_prompt=SKILL_CURATOR_SOURCE_ROUTING_SYSTEM_PROMPT,
        user_prompt=build_skill_curator_source_routing_user_prompt(
            run_id=run_id,
            domain_hint=domain_hint,
            inferred_tags=inferred_tags,
            qa_rejection_count=qa_rejection_count,
            qa_reasons=qa_reasons,
            supervisor_decisions=supervisor_decisions,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
        fallback_system_prompt=SKILL_CURATOR_SOURCE_ROUTING_SYSTEM_PROMPT,
        fallback_user_prompt=build_skill_curator_source_routing_fallback_user_prompt(
            run_id=run_id,
            domain_hint=domain_hint,
            inferred_tags=inferred_tags,
            qa_rejection_count=qa_rejection_count,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
    )
    if llm_response.error is not None:
        log.info("skill_curator.source_routing.finish", candidate_count=0, has_error=True)
        return CuratorGeneratorResult(candidates=[], llm_response=llm_response, error=llm_response.error)

    candidates, normalize_error = _normalize_output(llm_response.content)
    normalized_candidates = [item.model_copy(update={"tags": inferred_tags}) for item in candidates]
    log.info(
        "skill_curator.source_routing.finish",
        candidate_count=len(normalized_candidates) if normalize_error is None else 0,
        has_error=normalize_error is not None,
    )
    return CuratorGeneratorResult(
        candidates=normalized_candidates,
        llm_response=llm_response,
        error=normalize_error,
    )

