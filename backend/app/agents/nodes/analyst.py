from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from models.artifact import Artifact
from models.step import Step
from schemas.ids import make_id
from schemas.supervisor import Analyze


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("AgentState.session_factory is required for analyst node.")
    return session_factory


async def analyst_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for analyst node.")

    session_factory = _require_session_factory(state)
    request = Analyze.model_validate(state.get("pending_tool_args", {}))
    step_id = make_id("step_")

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="analyst",
            status="running",
            retry_count=0,
            payload=request.model_dump(),
        )
        session.add(step)
        await session.flush()
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="analysis_result",
                uri=f"memory://analysis/{run_id}/{step_id}",
                sha256=None,
                size_bytes=None,
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    return {
        **state,
        "analysis_done": True,
        "pending_tool_args": {},
        "last_completed_node": "analyst",
        "status": "running",
    }
