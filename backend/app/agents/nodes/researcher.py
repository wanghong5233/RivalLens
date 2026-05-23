from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.step import Step
from schemas.ids import make_id
from schemas.supervisor import ConductResearch


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("AgentState.session_factory is required for researcher node.")
    return session_factory


async def researcher_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for researcher node.")

    session_factory = _require_session_factory(state)
    request = ConductResearch.model_validate(state.get("pending_tool_args", {}))
    step_id = make_id("step_")
    collected_at = datetime.now(timezone.utc)

    evidence_text = (
        f"Skeleton research fragment for {request.competitor_id} on "
        f"dimensions={','.join(request.focus_dimensions or ['feature'])}."
    )

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="researcher",
            status="running",
            retry_count=0,
            payload=request.model_dump(),
        )
        session.add(step)
        await session.flush()
        session.add(
            EvidenceRecord(
                id=make_id("ev_"),
                run_id=run_id,
                source_type="offline_snapshot",
                source_url=None,
                source_title=f"{request.competitor_id} skeleton snapshot",
                quote=evidence_text,
                sanitized_text=evidence_text,
                span={"mode": "skeleton"},
                collected_by=step_id,
                collected_at=collected_at,
                desensitized=True,
            )
        )
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="research_fragment",
                uri=f"memory://research/{run_id}/{request.competitor_id}",
                sha256=None,
                size_bytes=None,
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    researched_competitors = list(state.get("researched_competitors", []))
    if request.competitor_id not in researched_competitors:
        researched_competitors.append(request.competitor_id)

    return {
        **state,
        "researched_competitors": researched_competitors,
        "pending_tool_args": {},
        "last_completed_node": "researcher",
        "status": "running",
    }
