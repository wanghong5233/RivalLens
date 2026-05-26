from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median

from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.run import Run
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord


@dataclass(frozen=True)
class RunMetricsSnapshot:
    run_id: str
    coverage_rate: float
    evidence_count_total: int
    evidence_count_by_competitor: dict[str, int]
    source_type_distribution: dict[str, int]
    desensitization_coverage: float
    qa_total_steps: int
    qa_rejected_steps: int
    qa_rejection_rate: float
    supervisor_iterations: int
    llm_token_total: int
    llm_call_count: int
    llm_latency_p50_ms: int | None
    manual_review_rate: float
    manual_review_is_proxy: bool
    run_wall_clock_seconds: int | None


def _extract_competitor_id(span: dict[str, object] | None) -> str | None:
    if not isinstance(span, dict):
        return None
    competitor_id = span.get("competitor_id")
    return competitor_id if isinstance(competitor_id, str) else None


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)


def _calc_latency_p50_ms(llm_rows: list[LLMCall]) -> int | None:
    latencies = [row.latency_ms for row in llm_rows if isinstance(row.latency_ms, int)]
    if not latencies:
        return None
    return int(median(latencies))


def build_run_metrics_snapshot(
    *,
    run: Run,
    evidence_rows: list[EvidenceRecord],
    step_rows: list[Step],
    llm_rows: list[LLMCall],
    decision_rows: list[SupervisorDecisionRecord],
    candidate_rows: list[SkillCandidateRecord],
) -> RunMetricsSnapshot:
    run_competitors = [competitor for competitor in run.competitors if isinstance(competitor, str)]
    evidence_count_by_competitor: dict[str, int] = {competitor: 0 for competitor in run_competitors}
    source_type_distribution = dict(Counter(row.source_type for row in evidence_rows))

    for row in evidence_rows:
        competitor_id = _extract_competitor_id(row.span)
        if competitor_id is None:
            continue
        evidence_count_by_competitor[competitor_id] = (
            evidence_count_by_competitor.get(competitor_id, 0) + 1
        )

    covered_competitor_count = sum(
        1 for competitor in run_competitors if evidence_count_by_competitor.get(competitor, 0) > 0
    )
    coverage_rate = _safe_rate(covered_competitor_count, len(run_competitors))

    desensitized_count = sum(1 for row in evidence_rows if row.desensitized)
    desensitization_coverage = _safe_rate(desensitized_count, len(evidence_rows))

    qa_steps = [step for step in step_rows if step.agent_name == "qa"]
    qa_rejected_steps = [
        step
        for step in qa_steps
        if step.rejection_reason is not None or step.status == "rejected"
    ]
    qa_rejection_rate = _safe_rate(len(qa_rejected_steps), len(qa_steps))

    supervisor_iterations = max((row.iteration for row in decision_rows), default=0)
    llm_token_total = sum(
        (row.prompt_tokens or 0) + (row.completion_tokens or 0) for row in llm_rows
    )

    supporting_candidates = []
    for candidate in candidate_rows:
        supporting_run_ids = [
            run_id for run_id in candidate.supporting_run_ids if isinstance(run_id, str)
        ]
        if run.run_id in supporting_run_ids:
            supporting_candidates.append(candidate)
    reviewed_candidates_count = sum(
        1 for candidate in supporting_candidates if candidate.reviewed_by is not None
    )
    manual_review_rate = _safe_rate(reviewed_candidates_count, len(supporting_candidates))

    run_wall_clock_seconds: int | None = None
    if run.finished_at is not None:
        delta = int((run.finished_at - run.started_at).total_seconds())
        run_wall_clock_seconds = max(delta, 0)

    return RunMetricsSnapshot(
        run_id=run.run_id,
        coverage_rate=coverage_rate,
        evidence_count_total=len(evidence_rows),
        evidence_count_by_competitor=evidence_count_by_competitor,
        source_type_distribution=source_type_distribution,
        desensitization_coverage=desensitization_coverage,
        qa_total_steps=len(qa_steps),
        qa_rejected_steps=len(qa_rejected_steps),
        qa_rejection_rate=qa_rejection_rate,
        supervisor_iterations=supervisor_iterations,
        llm_token_total=llm_token_total,
        llm_call_count=len(llm_rows),
        llm_latency_p50_ms=_calc_latency_p50_ms(llm_rows),
        manual_review_rate=manual_review_rate,
        manual_review_is_proxy=True,
        run_wall_clock_seconds=run_wall_clock_seconds,
    )
