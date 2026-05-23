from __future__ import annotations

from datetime import datetime, timezone

from agents.state import AgentState
from schemas.ids import make_id
from schemas.supervisor import Finalize, SupervisorDecision


def supervisor_node(state: AgentState) -> AgentState:
    now = datetime.now(timezone.utc).isoformat()
    run_id = state.get("run_id", make_id("run_"))
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
    return {
        **state,
        "run_id": run_id,
        "decisions": decisions,
        "status": "stub_finalized",
    }
