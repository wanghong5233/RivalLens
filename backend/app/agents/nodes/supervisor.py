from __future__ import annotations

from datetime import datetime, timezone

from agents.state import AgentState
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from schemas.ids import make_id
from schemas.supervisor import Finalize, SupervisorDecision


async def supervisor_node(state: AgentState) -> AgentState:
    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("AgentState.session_factory is required for supervisor persistence.")

    now = datetime.now(timezone.utc).isoformat()
    run_id = state.get("run_id", make_id("run_"))
    step_id = make_id("step_")
    finalize = Finalize(completion_reason="user_requested_stop", notes="walking skeleton")
    decision = SupervisorDecision(
        id=make_id("decision_"),
        run_id=run_id,
        iteration=1,
        chosen_tool="Finalize",
        tool_args=finalize.model_dump(),
        reasoning_summary="Skeleton mode uses an immediate finalize decision.",
        triggered_by="user_query",
        outcome="succeeded",
        outcome_recorded_at=now,
        created_at=now,
    )
    decisions = list(state.get("decisions", []))
    decisions.append(decision)

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="supervisor",
            status="running",
            retry_count=0,
            payload={"chosen_tool": decision.chosen_tool},
        )
        session.add(step)
        session.add(
            SupervisorDecisionRecord(
                id=decision.id,
                run_id=run_id,
                iteration=decision.iteration,
                chosen_tool=decision.chosen_tool,
                tool_args=decision.tool_args,
                reasoning_summary=decision.reasoning_summary,
                triggered_by=decision.triggered_by,
                outcome=decision.outcome,
                outcome_recorded_at=datetime.fromisoformat(decision.outcome_recorded_at)
                if decision.outcome_recorded_at is not None
                else None,
                created_at=datetime.fromisoformat(decision.created_at),
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    return {
        **state,
        "run_id": run_id,
        "decisions": decisions,
        "status": "completed",
    }
