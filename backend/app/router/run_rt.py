from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from agents.graph import get_graph
from db.engine import get_session_factory
from exceptions.base import APIException
from models.run import Run
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from schemas.ids import make_id

router = APIRouter()


class RunCreateRequest(BaseModel):
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


@router.post("/api/runs", response_model=RunCreateResponse)
async def create_run(payload: RunCreateRequest) -> RunCreateResponse:
    run_id = make_id("run_")
    session_factory = get_session_factory()

    async with session_factory() as session:
        session.add(
            Run(
                run_id=run_id,
                user_query="skeleton",
                industry_pack=payload.industry_pack,
                status="running",
                target_roles=payload.target_roles,
                competitors=payload.competitors,
            )
        )
        await session.commit()

    graph = get_graph()
    await graph.ainvoke(
        {
            "run_id": run_id,
            "industry_pack": payload.industry_pack,
            "competitors": payload.competitors,
            "user_query": "skeleton",
            "session_factory": session_factory,
        }
    )

    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=500,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} should exist after creation",
            )
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()

    return RunCreateResponse(
        run_id=run_id,
        status="completed",
        message="Walking skeleton run persisted.",
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
