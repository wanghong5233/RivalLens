from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.engine import get_session_factory
from exceptions.base import APIException
from models.run import Run
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from schemas.ids import make_id
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry

router = APIRouter()


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


@router.post("/api/runs", response_model=RunCreateResponse)
async def create_run(payload: RunCreateRequest, request: Request) -> RunCreateResponse:
    _validate_pack_and_competitors(payload)
    run_id = make_id("run_")
    session_factory = get_session_factory()

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

    return RunCreateResponse(
        run_id=run_id,
        status=run.status,
        message="Supervisor loop run persisted.",
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


@router.get("/api/runs/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(run_id: str) -> RunTraceResponse:
    session_factory = get_session_factory()
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
