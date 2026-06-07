from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.comparison import ComparisonCellRecord
from models.conclusion import ConclusionRecord
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.report import Report
from models.run import Run
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from schemas.contracts import validate_dimension


def _normalize_dimension(value: str) -> str | None:
    try:
        return validate_dimension(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class RunMetricsSnapshot:
    run_id: str
    coverage_rate: float
    evidence_count_total: int
    evidence_count_by_competitor: dict[str, int]
    evidence_count_by_dimension: dict[str, int]
    comparison_dimensions: list[str]
    conclusion_sections: list[str]
    report_section_ids: list[str]
    dimension_coverage_rate: float
    report_char_count: int
    report_section_count: int
    report_depth: str
    report_section_coverage_rate: float
    source_type_distribution: dict[str, int]
    desensitization_coverage: float
    qa_total_steps: int
    qa_rejected_steps: int
    qa_rejection_rate: float
    supervisor_iterations: int
    llm_token_total: int
    llm_call_count: int
    llm_latency_p50_ms: int | None
    llm_provider_error_count: int
    llm_retry_total: int
    manual_review_rate: float
    manual_review_is_proxy: bool
    run_wall_clock_seconds: int | None


def _extract_competitor_id(span: dict[str, object] | None) -> str | None:
    if not isinstance(span, dict):
        return None
    competitor_id = span.get("competitor_id")
    return competitor_id if isinstance(competitor_id, str) else None


def _extract_dimension(span: dict[str, object] | None) -> str | None:
    if not isinstance(span, dict):
        return None
    dimension = span.get("dimension")
    return _normalize_dimension(dimension) if isinstance(dimension, str) and dimension else None


def _expected_dimensions_from_plan_tree(plan_tree: dict[str, object] | None) -> set[str]:
    if not isinstance(plan_tree, dict):
        return set()
    tasks_raw = plan_tree.get("tasks")
    if not isinstance(tasks_raw, list):
        return set()
    dimensions: set[str] = set()
    for task_raw in tasks_raw:
        if not isinstance(task_raw, dict):
            continue
        focus_raw = task_raw.get("focus_dimensions")
        if not isinstance(focus_raw, list):
            continue
        for item in focus_raw:
            if isinstance(item, str) and item:
                normalized = _normalize_dimension(item)
                if normalized is not None:
                    dimensions.add(normalized)
    return dimensions


def _add_focus_dimensions_from_mapping(
    *,
    dimensions: set[str],
    payload: dict[str, object],
) -> None:
    focus_raw = payload.get("focus_dimensions")
    if isinstance(focus_raw, list):
        for item in focus_raw:
            if isinstance(item, str) and item:
                normalized = _normalize_dimension(item)
                if normalized is not None:
                    dimensions.add(normalized)
    topics_raw = payload.get("topics")
    if not isinstance(topics_raw, list):
        return
    for topic_raw in topics_raw:
        if isinstance(topic_raw, dict):
            _add_focus_dimensions_from_mapping(dimensions=dimensions, payload=topic_raw)


def _expected_dimensions_from_decisions(
    decision_rows: list[SupervisorDecisionRecord],
) -> set[str]:
    dimensions: set[str] = set()
    for decision in decision_rows:
        tool_args = decision.tool_args
        if isinstance(tool_args, dict):
            _add_focus_dimensions_from_mapping(dimensions=dimensions, payload=tool_args)
    return dimensions


def _report_depth_from_run(run: Run) -> str:
    if isinstance(run.intake_draft, dict):
        depth_raw = run.intake_draft.get("report_depth")
        if depth_raw in {"quick", "deep"}:
            return str(depth_raw)
    return "quick"


def _latest_report(report_rows: list[Report]) -> Report | None:
    if not report_rows:
        return None
    return max(report_rows, key=lambda row: row.created_at)


def _section_ids_from_report(report: Report | None) -> set[str]:
    if report is None or not isinstance(report.content_json, dict):
        return set()
    content_json = report.content_json
    sections_raw = report.content_json.get("sections")
    section_ids: set[str] = set()
    if isinstance(sections_raw, list):
        for section_raw in sections_raw:
            if not isinstance(section_raw, dict):
                continue
            section_id_raw = section_raw.get("section_id")
            if isinstance(section_id_raw, str) and section_id_raw:
                normalized = _normalize_dimension(section_id_raw)
                if normalized is not None:
                    section_ids.add(normalized)
    executive_summary_raw = content_json.get("executive_summary")
    if isinstance(executive_summary_raw, str) and executive_summary_raw.strip():
        section_ids.add("executive_summary")
    return section_ids


def _dimensions_from_comparisons(rows: list[ComparisonCellRecord]) -> set[str]:
    return {
        normalized
        for row in rows
        if isinstance(row.dimension, str) and row.dimension
        for normalized in [_normalize_dimension(row.dimension)]
        if normalized is not None
    }


def _sections_from_conclusions(rows: list[ConclusionRecord]) -> set[str]:
    return {
        normalized
        for row in rows
        if isinstance(row.section, str) and row.section
        for normalized in [_normalize_dimension(row.section)]
        if normalized is not None
    }


def _section_count_from_report(report: Report | None) -> int:
    if report is None or not isinstance(report.content_json, dict):
        return 0
    sections_raw = report.content_json.get("sections")
    return len(sections_raw) if isinstance(sections_raw, list) else 0


def _latest_writer_target_sections(step_rows: list[Step]) -> set[str]:
    writer_steps = [row for row in step_rows if row.agent_name == "writer"]
    if not writer_steps:
        return set()
    latest_writer = max(writer_steps, key=lambda row: row.created_at)
    if not isinstance(latest_writer.payload, dict):
        return set()
    sections_raw = latest_writer.payload.get("target_sections")
    if not isinstance(sections_raw, list):
        sections_raw = latest_writer.payload.get("sections")
    if not isinstance(sections_raw, list):
        return set()
    return {
        normalized
        for item in sections_raw
        if isinstance(item, str) and item
        for normalized in [_normalize_dimension(item)]
        if normalized is not None
    }


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
    report_rows: list[Report] | None = None,
    comparison_rows: list[ComparisonCellRecord] | None = None,
    conclusion_rows: list[ConclusionRecord] | None = None,
) -> RunMetricsSnapshot:
    run_competitors = [competitor for competitor in run.competitors if isinstance(competitor, str)]
    evidence_count_by_competitor: dict[str, int] = {competitor: 0 for competitor in run_competitors}
    expected_dimensions = _expected_dimensions_from_plan_tree(run.plan_tree)
    if not expected_dimensions:
        expected_dimensions = _expected_dimensions_from_decisions(decision_rows)
    evidence_count_by_dimension: dict[str, int] = {
        dimension: 0 for dimension in sorted(expected_dimensions)
    }
    source_type_distribution = dict(Counter(row.source_type for row in evidence_rows))

    for row in evidence_rows:
        competitor_id = _extract_competitor_id(row.span)
        if competitor_id is not None:
            evidence_count_by_competitor[competitor_id] = (
                evidence_count_by_competitor.get(competitor_id, 0) + 1
            )
        dimension = _extract_dimension(row.span)
        if dimension is not None:
            evidence_count_by_dimension[dimension] = (
                evidence_count_by_dimension.get(dimension, 0) + 1
            )

    covered_competitor_count = sum(
        1 for competitor in run_competitors if evidence_count_by_competitor.get(competitor, 0) > 0
    )
    coverage_rate = _safe_rate(covered_competitor_count, len(run_competitors))
    evidence_dimensions = {
        dimension
        for dimension, count in evidence_count_by_dimension.items()
        if count > 0
    }
    latest_report = _latest_report(report_rows or [])
    report_section_ids = _section_ids_from_report(latest_report)
    comparison_dimensions = _dimensions_from_comparisons(comparison_rows or [])
    conclusion_sections = _sections_from_conclusions(conclusion_rows or [])
    downstream_dimensions = comparison_dimensions | conclusion_sections | report_section_ids
    dimension_denominator = expected_dimensions or downstream_dimensions or evidence_dimensions
    covered_dimension_count = (
        sum(1 for dimension in expected_dimensions if dimension in downstream_dimensions)
        if expected_dimensions
        else len(dimension_denominator)
    )
    dimension_coverage_rate = _safe_rate(covered_dimension_count, len(dimension_denominator))
    expected_report_sections = _latest_writer_target_sections(step_rows) or expected_dimensions
    report_section_coverage_rate = (
        _safe_rate(
            sum(1 for section_id in expected_report_sections if section_id in report_section_ids),
            len(expected_report_sections),
        )
        if expected_report_sections
        else 0.0
    )

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
    llm_provider_error_count = sum(1 for row in llm_rows if row.error is not None)
    llm_retry_total = sum(row.retry_count or 0 for row in llm_rows)

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
        evidence_count_by_dimension=evidence_count_by_dimension,
        comparison_dimensions=sorted(comparison_dimensions),
        conclusion_sections=sorted(conclusion_sections),
        report_section_ids=sorted(report_section_ids),
        dimension_coverage_rate=dimension_coverage_rate,
        report_char_count=len(latest_report.content_markdown.strip()) if latest_report is not None else 0,
        report_section_count=_section_count_from_report(latest_report),
        report_depth=_report_depth_from_run(run),
        report_section_coverage_rate=report_section_coverage_rate,
        source_type_distribution=source_type_distribution,
        desensitization_coverage=desensitization_coverage,
        qa_total_steps=len(qa_steps),
        qa_rejected_steps=len(qa_rejected_steps),
        qa_rejection_rate=qa_rejection_rate,
        supervisor_iterations=supervisor_iterations,
        llm_token_total=llm_token_total,
        llm_call_count=len(llm_rows),
        llm_latency_p50_ms=_calc_latency_p50_ms(llm_rows),
        llm_provider_error_count=llm_provider_error_count,
        llm_retry_total=llm_retry_total,
        manual_review_rate=manual_review_rate,
        manual_review_is_proxy=True,
        run_wall_clock_seconds=run_wall_clock_seconds,
    )


async def load_run_metrics_snapshot(
    *,
    session: AsyncSession,
    run_id: str,
) -> RunMetricsSnapshot:
    run = await session.get(Run, run_id)
    if run is None:
        raise RuntimeError(f"run_id={run_id} does not exist")

    evidence_rows = (
        await session.execute(
            select(EvidenceRecord)
            .where(EvidenceRecord.run_id == run_id)
            .order_by(EvidenceRecord.created_at.asc())
        )
    ).scalars().all()
    step_rows = (
        await session.execute(
            select(Step).where(Step.run_id == run_id).order_by(Step.created_at.asc())
        )
    ).scalars().all()
    llm_rows = (
        await session.execute(
            select(LLMCall)
            .join(Step, LLMCall.step_id == Step.step_id)
            .where(Step.run_id == run_id)
            .order_by(LLMCall.created_at.asc())
        )
    ).scalars().all()
    decision_rows = (
        await session.execute(
            select(SupervisorDecisionRecord)
            .where(SupervisorDecisionRecord.run_id == run_id)
            .order_by(SupervisorDecisionRecord.created_at.asc())
        )
    ).scalars().all()
    report_rows = (
        await session.execute(
            select(Report)
            .where(Report.run_id == run_id)
            .order_by(Report.created_at.asc())
        )
    ).scalars().all()
    comparison_rows = (
        await session.execute(
            select(ComparisonCellRecord)
            .where(ComparisonCellRecord.run_id == run_id)
            .order_by(
                ComparisonCellRecord.dimension.asc(),
                ComparisonCellRecord.competitor_id.asc(),
                ComparisonCellRecord.created_at.asc(),
            )
        )
    ).scalars().all()
    conclusion_rows = (
        await session.execute(
            select(ConclusionRecord)
            .where(ConclusionRecord.run_id == run_id)
            .order_by(ConclusionRecord.created_at.asc(), ConclusionRecord.conclusion_id.asc())
        )
    ).scalars().all()
    candidate_rows = (await session.execute(select(SkillCandidateRecord))).scalars().all()
    candidate_rows = [
        row
        for row in candidate_rows
        if run_id in (row.supporting_run_ids if isinstance(row.supporting_run_ids, list) else [])
    ]

    return build_run_metrics_snapshot(
        run=run,
        evidence_rows=list(evidence_rows),
        step_rows=list(step_rows),
        llm_rows=list(llm_rows),
        decision_rows=list(decision_rows),
        candidate_rows=list(candidate_rows),
        report_rows=list(report_rows),
        comparison_rows=list(comparison_rows),
        conclusion_rows=list(conclusion_rows),
    )
