from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Sequence

from service.llm.response import LLMResponse
from service.skill_curator.generators import (
    generate_prompt_template_candidates,
    generate_qa_rule_candidates,
    generate_source_routing_candidates,
)
from service.skill_curator.models import SkillCuratorCandidate
from utils.logger import get_logger

log = get_logger("service.skill_curator.engine")


@dataclass(slots=True)
class SkillCuratorGenerationResult:
    candidates: list[SkillCuratorCandidate]
    llm_response: LLMResponse
    error: str | None


def _count_candidates(candidates: Sequence[SkillCuratorCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item.candidate_type] = counts.get(item.candidate_type, 0) + 1
    return counts


def _pick_primary_llm_response(
    *,
    qa_rule_response: LLMResponse,
    prompt_template_response: LLMResponse,
    source_routing_response: LLMResponse,
) -> LLMResponse:
    if qa_rule_response.error is None:
        return qa_rule_response
    if prompt_template_response.error is None:
        return prompt_template_response
    return source_routing_response


async def generate_skill_candidates(
    *,
    run_id: str,
    domain_hint: str | None,
    qa_rejection_count: int,
    qa_reasons: Sequence[str],
    supervisor_decisions: Sequence[dict[str, object]],
    evidence_source_counts: dict[str, int],
    total_evidence_count: int,
) -> SkillCuratorGenerationResult:
    log.info(
        "skill_curator.candidate.start",
        run_id=run_id,
        domain_hint=domain_hint,
        qa_rejection_count=qa_rejection_count,
        total_evidence_count=total_evidence_count,
    )
    qa_rule_result, prompt_template_result, source_routing_result = await asyncio.gather(
        generate_qa_rule_candidates(
            run_id=run_id,
            domain_hint=domain_hint,
            qa_rejection_count=qa_rejection_count,
            qa_reasons=qa_reasons,
            supervisor_decisions=supervisor_decisions,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
        generate_prompt_template_candidates(
            run_id=run_id,
            domain_hint=domain_hint,
            qa_rejection_count=qa_rejection_count,
            qa_reasons=qa_reasons,
            supervisor_decisions=supervisor_decisions,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
        generate_source_routing_candidates(
            run_id=run_id,
            domain_hint=domain_hint,
            qa_rejection_count=qa_rejection_count,
            qa_reasons=qa_reasons,
            supervisor_decisions=supervisor_decisions,
            evidence_source_counts=evidence_source_counts,
            total_evidence_count=total_evidence_count,
        ),
    )

    generator_results = [qa_rule_result, prompt_template_result, source_routing_result]
    candidates: list[SkillCuratorCandidate] = []
    errors: list[str] = []
    for item in generator_results:
        candidates.extend(item.candidates)
        if item.error is not None:
            errors.append(item.error)

    llm_response = _pick_primary_llm_response(
        qa_rule_response=qa_rule_result.llm_response,
        prompt_template_response=prompt_template_result.llm_response,
        source_routing_response=source_routing_result.llm_response,
    )
    normalize_error = "; ".join(errors) if errors else None
    if normalize_error is not None and not candidates:
        log.info(
            "skill_curator.candidate.finish",
            candidate_count=0,
            candidate_count_by_type={},
            has_error=True,
        )
        return SkillCuratorGenerationResult(
            candidates=[],
            llm_response=llm_response,
            error=normalize_error,
        )

    log.info(
        "skill_curator.candidate.finish",
        candidate_count=len(candidates),
        candidate_count_by_type=_count_candidates(candidates),
        has_error=normalize_error is not None and not candidates,
    )
    return SkillCuratorGenerationResult(
        candidates=candidates,
        llm_response=llm_response,
        error=normalize_error if not candidates else None,
    )
