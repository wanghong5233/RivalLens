from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.graph import get_graph
from db.engine import get_session_factory
from exceptions.base import APIException
from models.run import Run
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
