from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from models.artifact import Artifact
from models.report import Report
from models.step import Step
from schemas.ids import make_id
from schemas.supervisor import Write


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("AgentState.session_factory is required for writer node.")
    return session_factory


async def writer_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for writer node.")

    session_factory = _require_session_factory(state)
    request = Write.model_validate(state.get("pending_tool_args", {}))
    step_id = make_id("step_")
    report_id = f"report_{uuid4().hex[:12]}"
    markdown = (
        "# RivalLens Skeleton Report\n\n"
        f"- template_id: {request.template_id}\n"
        f"- sections: {request.sections or []}\n"
    )

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="writer",
            status="running",
            retry_count=0,
            payload=request.model_dump(),
        )
        session.add(step)
        await session.flush()
        session.add(
            Report(
                report_id=report_id,
                run_id=run_id,
                status="completed",
                content_json={
                    "template_id": request.template_id,
                    "sections": request.sections or [],
                },
                content_markdown=markdown,
            )
        )
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="report_draft",
                uri=f"memory://report/{run_id}/{report_id}",
                sha256=None,
                size_bytes=None,
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    return {
        **state,
        "report_draft_done": True,
        "pending_tool_args": {},
        "pending_review_target_step_id": step_id,
        "status": "running",
    }
