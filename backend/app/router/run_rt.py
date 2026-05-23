from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter

from agents.graph import get_graph
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
    graph = get_graph()
    await graph.ainvoke(
        {
            "run_id": run_id,
            "industry_pack": payload.industry_pack,
            "competitors": payload.competitors,
            "user_query": "skeleton",
        }
    )
    return RunCreateResponse(
        run_id=run_id,
        status="stub",
        message="Walking skeleton run accepted.",
    )
