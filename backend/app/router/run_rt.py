from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from db.engine import get_session_factory
from exceptions.base import APIException
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.report import Report
from models.run import Run
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from schemas.ids import make_id
from service.conclusion import load_conclusions_for_run
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry
from service.metrics import build_run_metrics_snapshot
from utils.logger import bind_run, get_logger

router = APIRouter()
log = get_logger("router.run_rt")


class RunCreateRequest(BaseModel):
    user_query: str = "skeleton"
    competitors: list[str] = Field(default_factory=list)
    industry_pack: str
    target_roles: list[str] = Field(default_factory=list)


class RunCreateResponse(BaseModel):
    run_id: str
    status: str
    message: str


class RunDetailResponse(BaseModel):
    run_id: str
    user_query: str
    industry_pack: str
    status: str
    target_roles: list[str]
    competitors: list[str]
    started_at: str
    finished_at: str | None
    created_at: str


class RunListItemResponse(BaseModel):
    run_id: str
    user_query: str
    industry_pack: str
    status: str
    started_at: str
    finished_at: str | None
    created_at: str
    step_count: int
    evidence_count: int
    has_report: bool


class RunListResponse(BaseModel):
    items: list[RunListItemResponse]
    total: int
    limit: int
    offset: int


class StepTraceResponse(BaseModel):
    step_id: str
    run_id: str
    agent_name: str
    status: str
    retry_count: int
    payload: dict[str, object]
    started_at: str
    finished_at: str | None
    created_at: str


class SupervisorDecisionTraceResponse(BaseModel):
    id: str
    run_id: str
    iteration: int
    chosen_tool: str
    tool_args: dict[str, object]
    reasoning_summary: str
    triggered_by: str | None
    outcome: str | None
    outcome_recorded_at: str | None
    created_at: str


class RunTraceResponse(BaseModel):
    run: RunDetailResponse
    steps: list[StepTraceResponse]
    supervisor_decisions: list[SupervisorDecisionTraceResponse]


class EvidenceBriefResponse(BaseModel):
    evidence_id: str
    source_type: str
    source_url: str | None
    source_title: str | None
    competitor_id: str | None


class RunReportResponse(BaseModel):
    run_id: str
    status: str
    content_markdown: str
    content_json: dict[str, object]
    generated_at: str
    evidence_id_to_brief: dict[str, EvidenceBriefResponse]


class EvidenceListItemResponse(BaseModel):
    evidence_id: str
    run_id: str
    source_type: str
    source_url: str | None
    source_title: str | None
    sanitized_text: str
    competitor_id: str | None
    metadata: dict[str, object] | None
    collected_at: str
    created_at: str


class RunMetricsResponse(BaseModel):
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


class ConclusionItemResponse(BaseModel):
    conclusion_id: str
    run_id: str
    step_id: str
    section: str
    claim: str
    confidence: str
    competitor_ids: list[str]
    risk_flags: list[str]
    evidence_ids: list[str]
    created_at: str


class RunConclusionsResponse(BaseModel):
    run_id: str
    items: list[ConclusionItemResponse]


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _to_run_detail(run: Run) -> RunDetailResponse:
    return RunDetailResponse(
        run_id=run.run_id,
        user_query=run.user_query,
        industry_pack=run.industry_pack,
        status=run.status,
        target_roles=list(run.target_roles),
        competitors=list(run.competitors),
        started_at=run.started_at.isoformat(),
        finished_at=_to_iso(run.finished_at),
        created_at=run.created_at.isoformat(),
    )


def _extract_competitor_id(span: dict[str, object] | None) -> str | None:
    if not isinstance(span, dict):
        return None
    competitor_id = span.get("competitor_id")
    return competitor_id if isinstance(competitor_id, str) else None


def _validate_pack_and_competitors(payload: RunCreateRequest) -> None:
    pack_registry = get_industry_pack_registry()
    if not pack_registry.has(payload.industry_pack):
        raise APIException(
            status_code=400,
            error_code="INDUSTRY_PACK_NOT_FOUND",
            message=f"industry_pack={payload.industry_pack} is not loaded.",
        )

    try:
        pack = pack_registry.get(payload.industry_pack)
    except IndustryPackNotFound as exc:
        raise APIException(
            status_code=400,
            error_code="INDUSTRY_PACK_NOT_FOUND",
            message=f"industry_pack={payload.industry_pack} is not loaded.",
        ) from exc

    missing_competitors = [item for item in payload.competitors if item not in pack.competitors]
    if missing_competitors:
        missing_joined = ",".join(missing_competitors)
        raise APIException(
            status_code=400,
            error_code="COMPETITOR_NOT_IN_PACK",
            message=f"competitor(s) {missing_joined} not found in pack {payload.industry_pack}.",
        )


@router.get("/api/runs", response_model=RunListResponse)
async def list_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    normalized_status = status.strip() if isinstance(status, str) else None
    session_factory = get_session_factory()
    async with session_factory() as session:
        step_count_subquery = (
            select(func.count())
            .select_from(Step)
            .where(Step.run_id == Run.run_id)
            .scalar_subquery()
        )
        evidence_count_subquery = (
            select(func.count())
            .select_from(EvidenceRecord)
            .where(EvidenceRecord.run_id == Run.run_id)
            .scalar_subquery()
        )
        report_count_subquery = (
            select(func.count())
            .select_from(Report)
            .where(Report.run_id == Run.run_id)
            .scalar_subquery()
        )
        list_query = select(
            Run,
            step_count_subquery.label("step_count"),
            evidence_count_subquery.label("evidence_count"),
            report_count_subquery.label("report_count"),
        )
        total_query = select(func.count()).select_from(Run)
        if normalized_status:
            list_query = list_query.where(Run.status == normalized_status)
            total_query = total_query.where(Run.status == normalized_status)
        list_query = list_query.order_by(Run.started_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(list_query)).all()
        total = int((await session.execute(total_query)).scalar_one())

    items: list[RunListItemResponse] = []
    for run, step_count, evidence_count, report_count in rows:
        items.append(
            RunListItemResponse(
                run_id=run.run_id,
                user_query=run.user_query,
                industry_pack=run.industry_pack,
                status=run.status,
                started_at=run.started_at.isoformat(),
                finished_at=_to_iso(run.finished_at),
                created_at=run.created_at.isoformat(),
                step_count=int(step_count),
                evidence_count=int(evidence_count),
                has_report=int(report_count) > 0,
            )
        )
    return RunListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/api/runs", response_model=RunCreateResponse)
async def create_run(payload: RunCreateRequest, request: Request) -> RunCreateResponse:
    _validate_pack_and_competitors(payload)
    run_id = make_id("run_")
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info(
            "api.run.create.start",
            industry_pack=payload.industry_pack,
            competitor_count=len(payload.competitors),
            target_role_count=len(payload.target_roles),
        )

        async with session_factory() as session:
            session.add(
                Run(
                    run_id=run_id,
                    user_query=payload.user_query,
                    industry_pack=payload.industry_pack,
                    status="running",
                    target_roles=payload.target_roles,
                    competitors=payload.competitors,
                )
            )
            await session.commit()

        graph = getattr(request.app.state, "compiled_graph", None)
        if graph is None:
            raise APIException(
                status_code=500,
                error_code="GRAPH_NOT_INITIALIZED",
                message="Compiled LangGraph instance is not initialized.",
            )
        graph_state = await graph.ainvoke(
            {
                "run_id": run_id,
                "industry_pack": payload.industry_pack,
                "competitors": payload.competitors,
                "user_query": payload.user_query,
                "researched_competitors": [],
                "analysis_done": False,
                "report_draft_done": False,
                "current_iteration": 0,
                "pending_tool_args": {},
                "qa_outcome": None,
                "qa_reject_to": None,
                "qa_rejection_count": 0,
                "pending_review_target_step_id": None,
                "qa_reasons": [],
                "status": "running",
            },
            config={"configurable": {"thread_id": run_id}},
        )

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=500,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} should exist after creation",
                )
            run_status = str(graph_state.get("status", "completed"))
            run.status = run_status if run_status in {"completed", "degraded"} else "completed"
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
        log.info("api.run.create.finish", status=run.status)

    return RunCreateResponse(
        run_id=run_id,
        status=run.status,
        message="Supervisor loop run persisted.",
    )


@router.post("/api/runs/{run_id}/resume", response_model=RunCreateResponse)
async def resume_run(run_id: str, request: Request) -> RunCreateResponse:
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info("api.run.resume.start")
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )
            if run.status != "running":
                raise APIException(
                    status_code=409,
                    error_code="RUN_NOT_RESUMABLE",
                    message=f"run_id={run_id} status={run.status} cannot resume",
                )

        graph = getattr(request.app.state, "compiled_graph", None)
        if graph is None:
            raise APIException(
                status_code=500,
                error_code="GRAPH_NOT_INITIALIZED",
                message="Compiled LangGraph instance is not initialized.",
            )
        graph_state = await graph.ainvoke(None, config={"configurable": {"thread_id": run_id}})

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=500,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} should exist before resume update",
                )
            run_status = str(graph_state.get("status", "completed"))
            run.status = run_status if run_status in {"completed", "degraded"} else "completed"
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
        log.info("api.run.resume.finish", status=run.status)

    return RunCreateResponse(
        run_id=run_id,
        status=run.status,
        message="Run resumed from checkpoint.",
    )


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str) -> RunDetailResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        return _to_run_detail(run)


@router.get("/api/runs/{run_id}/report", response_model=RunReportResponse)
async def get_run_report(run_id: str) -> RunReportResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        report = (
            await session.execute(
                select(Report).where(Report.run_id == run_id).order_by(Report.created_at.desc()).limit(1)
            )
        ).scalars().first()
        if report is None:
            raise APIException(
                status_code=404,
                error_code="REPORT_NOT_FOUND",
                message=f"report for run_id={run_id} does not exist",
            )
        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()

    evidence_id_to_brief: dict[str, EvidenceBriefResponse] = {}
    for evidence in evidence_rows:
        evidence_id_to_brief[evidence.id] = EvidenceBriefResponse(
            evidence_id=evidence.id,
            source_type=evidence.source_type,
            source_url=evidence.source_url,
            source_title=evidence.source_title,
            competitor_id=_extract_competitor_id(evidence.span),
        )

    return RunReportResponse(
        run_id=run.run_id,
        status=run.status,
        content_markdown=report.content_markdown,
        content_json=report.content_json,
        generated_at=report.created_at.isoformat(),
        evidence_id_to_brief=evidence_id_to_brief,
    )


@router.get("/api/runs/{run_id}/evidence", response_model=list[EvidenceListItemResponse])
async def get_run_evidence(
    run_id: str,
    competitor_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
) -> list[EvidenceListItemResponse]:
    normalized_competitor_id = competitor_id.strip() if isinstance(competitor_id, str) else None
    normalized_source_type = source_type.strip() if isinstance(source_type, str) else None
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        query = select(EvidenceRecord).where(EvidenceRecord.run_id == run_id)
        if normalized_source_type:
            query = query.where(EvidenceRecord.source_type == normalized_source_type)
        evidence_rows = (
            await session.execute(query.order_by(EvidenceRecord.created_at.asc()))
        ).scalars().all()

    if normalized_competitor_id:
        evidence_rows = [
            item
            for item in evidence_rows
            if _extract_competitor_id(item.span) == normalized_competitor_id
        ]

    return [
        EvidenceListItemResponse(
            evidence_id=evidence.id,
            run_id=evidence.run_id,
            source_type=evidence.source_type,
            source_url=evidence.source_url,
            source_title=evidence.source_title,
            sanitized_text=evidence.sanitized_text,
            competitor_id=_extract_competitor_id(evidence.span),
            metadata=evidence.span,
            collected_at=evidence.collected_at.isoformat(),
            created_at=evidence.created_at.isoformat(),
        )
        for evidence in evidence_rows
    ]


@router.get("/api/runs/{run_id}/conclusions", response_model=RunConclusionsResponse)
async def get_run_conclusions(run_id: str) -> RunConclusionsResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        items_raw = await load_conclusions_for_run(session=session, run_id=run_id)

    return RunConclusionsResponse(
        run_id=run_id,
        items=[ConclusionItemResponse.model_validate(item) for item in items_raw],
    )


@router.get("/api/runs/{run_id}/metrics", response_model=RunMetricsResponse)
async def get_run_metrics(run_id: str) -> RunMetricsResponse:
    """
    Runtime business-loop metrics for scoring and demo checkpoints.

    manual_review_rate is a proxy metric based on reviewed skill candidates
    linked to this run, not direct evaluator edits on report content.
    """

    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )

        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()
        step_rows = (
            await session.execute(select(Step).where(Step.run_id == run_id).order_by(Step.created_at.asc()))
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
        candidate_rows = (
            await session.execute(
                select(SkillCandidateRecord).where(SkillCandidateRecord.industry_pack == run.industry_pack)
            )
        ).scalars().all()

    snapshot = build_run_metrics_snapshot(
        run=run,
        evidence_rows=evidence_rows,
        step_rows=step_rows,
        llm_rows=llm_rows,
        decision_rows=decision_rows,
        candidate_rows=candidate_rows,
    )
    return RunMetricsResponse(**asdict(snapshot))


@router.get("/api/runs/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(run_id: str) -> RunTraceResponse:
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info("api.run.trace.query.start")
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )

            step_rows = (
                await session.execute(
                    select(Step).where(Step.run_id == run_id).order_by(Step.created_at.asc())
                )
            ).scalars().all()
            decision_rows = (
                await session.execute(
                    select(SupervisorDecisionRecord)
                    .where(SupervisorDecisionRecord.run_id == run_id)
                    .order_by(SupervisorDecisionRecord.created_at.asc())
                )
            ).scalars().all()
        log.info(
            "api.run.trace.query.finish",
            step_count=len(step_rows),
            decision_count=len(decision_rows),
        )

    return RunTraceResponse(
        run=_to_run_detail(run),
        steps=[
            StepTraceResponse(
                step_id=step.step_id,
                run_id=step.run_id,
                agent_name=step.agent_name,
                status=step.status,
                retry_count=step.retry_count,
                payload=step.payload,
                started_at=step.started_at.isoformat(),
                finished_at=_to_iso(step.finished_at),
                created_at=step.created_at.isoformat(),
            )
            for step in step_rows
        ],
        supervisor_decisions=[
            SupervisorDecisionTraceResponse(
                id=decision.id,
                run_id=decision.run_id,
                iteration=decision.iteration,
                chosen_tool=decision.chosen_tool,
                tool_args=decision.tool_args,
                reasoning_summary=decision.reasoning_summary,
                triggered_by=decision.triggered_by,
                outcome=decision.outcome,
                outcome_recorded_at=_to_iso(decision.outcome_recorded_at),
                created_at=decision.created_at.isoformat(),
            )
            for decision in decision_rows
        ],
    )
