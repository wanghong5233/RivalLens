from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from service.llm.client import llm_client
from schemas.ids import make_id
from schemas.supervisor import Analyze, ConductResearch, Finalize, SupervisorDecision, Write

MAX_SUPERVISOR_ITERATIONS = 10
DEFAULT_RESEARCH_DIMENSIONS = ["feature", "pricing", "user_feedback"]
DEFAULT_WRITE_SECTIONS = ["feature", "pricing", "user_feedback", "differentiation", "swot"]
VALID_TOOLS = {"ConductResearch", "Analyze", "Write", "Finalize"}
TriggerSource = Literal[
    "user_query",
    "researcher_completion",
    "analyst_completion",
    "writer_completion",
    "qa_approval",
    "qa_rejection",
    "iteration_advance",
]


def _resolve_triggered_by(
    *,
    iteration: int,
    last_completed_node: Literal["researcher", "analyst", "writer"] | None,
    qa_outcome: Literal["approved", "rejected", "force_degraded"] | None,
) -> TriggerSource:
    if qa_outcome == "approved":
        return "qa_approval"
    if qa_outcome in {"rejected", "force_degraded"}:
        return "qa_rejection"
    if iteration == 1:
        return "user_query"
    if last_completed_node == "researcher":
        return "researcher_completion"
    if last_completed_node == "analyst":
        return "analyst_completion"
    if last_completed_node == "writer":
        return "writer_completion"
    return "iteration_advance"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fallback_decision(
    *,
    run_id: str,
    iteration: int,
    competitors: list[str],
    researched_competitors: list[str],
    analysis_done: bool,
    report_draft_done: bool,
    triggered_by: TriggerSource,
    user_query: str,
) -> SupervisorDecision:
    pending_competitors = [c for c in competitors if c not in researched_competitors]
    now = _now_iso()

    if pending_competitors:
        competitor_id = pending_competitors[0]
        args = ConductResearch(
            research_topic=f"{competitor_id} vs user_query={user_query}",
            competitor_id=competitor_id,
            focus_dimensions=DEFAULT_RESEARCH_DIMENSIONS,
            max_iterations=6,
            fallback_to_offline=True,
        ).model_dump()
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="ConductResearch",
            tool_args=args,
            reasoning_summary=f"Fallback planner selects pending competitor `{competitor_id}`.",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return decision

    if not analysis_done:
        args = Analyze(
            focus_dimensions=DEFAULT_RESEARCH_DIMENSIONS,
            parallel_by_dimension=False,
            require_cross_competitor=True,
        ).model_dump()
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Analyze",
            tool_args=args,
            reasoning_summary="Fallback planner moves to cross-competitor analysis.",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return decision

    if not report_draft_done:
        args = Write(
            template_id="battlecard_default",
            sections=DEFAULT_WRITE_SECTIONS,
        ).model_dump()
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Write",
            tool_args=args,
            reasoning_summary="Fallback planner composes report draft after analysis.",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return decision

    args = Finalize(
        completion_reason="all_dimensions_covered",
        notes="All planned skeleton phases are completed.",
    ).model_dump()
    decision = SupervisorDecision(
        id=make_id("decision_"),
        run_id=run_id,
        iteration=iteration,
        chosen_tool="Finalize",
        tool_args=args,
        reasoning_summary="Fallback planner finalizes after research/analysis/write phases.",
        triggered_by=triggered_by,
        outcome="succeeded",
        outcome_recorded_at=now,
        created_at=now,
    )
    return decision


def _decision_from_qa_feedback(
    *,
    run_id: str,
    iteration: int,
    triggered_by: TriggerSource,
    qa_outcome: Literal["approved", "rejected", "force_degraded"] | None,
    qa_reject_to: Literal["researcher", "analyst", "writer", "supervisor"] | None,
    qa_reasons: list[str],
) -> tuple[SupervisorDecision, dict[str, Any], bool] | None:
    if qa_outcome is None or qa_outcome == "approved":
        return None

    now = _now_iso()
    if qa_outcome == "force_degraded":
        note = "QA max retries hit; force finalize in degraded mode."
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Finalize",
            tool_args=Finalize(
                completion_reason="fallback_path",
                notes=note,
            ).model_dump(),
            reasoning_summary=note,
            triggered_by=triggered_by,
            outcome="succeeded",
            outcome_recorded_at=now,
            created_at=now,
        )
        return (
            decision,
            {"provider": "qa_guardrail", "prompt_preview": "qa_force_degraded"},
            True,
        )

    if qa_reject_to == "writer":
        qa_reason_summary = "; ".join(qa_reasons[:3]) or "QA blocking rules failed."
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Write",
            tool_args=Write(
                template_id="battlecard_default",
                sections=DEFAULT_WRITE_SECTIONS,
            ).model_dump(),
            reasoning_summary=f"QA rejected writer output and requests rewrite: {qa_reason_summary}",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return (
            decision,
            {"provider": "qa_guardrail", "prompt_preview": "qa_rejected_to_writer"},
            False,
        )

    note = (
        f"QA rejected output to `{qa_reject_to}` but this path is not implemented in fast-path slice; "
        "fallback to finalize degraded."
    )
    decision = SupervisorDecision(
        id=make_id("decision_"),
        run_id=run_id,
        iteration=iteration,
        chosen_tool="Finalize",
        tool_args=Finalize(
            completion_reason="fallback_path",
            notes=note,
        ).model_dump(),
        reasoning_summary=note,
        triggered_by=triggered_by,
        outcome="succeeded",
        outcome_recorded_at=now,
        created_at=now,
    )
    return (
        decision,
        {"provider": "qa_guardrail", "prompt_preview": "qa_rejected_unimplemented_target"},
        True,
    )


def _try_llm_decision(
    *,
    run_id: str,
    iteration: int,
    llm_response: dict[str, Any],
    triggered_by: TriggerSource,
) -> SupervisorDecision | None:
    content = llm_response.get("content")
    if not isinstance(content, dict):
        return None

    chosen_tool = content.get("chosen_tool")
    if not isinstance(chosen_tool, str) or chosen_tool not in VALID_TOOLS:
        return None

    tool_args_raw = content.get("tool_args")
    if not isinstance(tool_args_raw, dict):
        return None

    chosen_tool_literal: Literal["ConductResearch", "Analyze", "Write", "Finalize"]
    try:
        if chosen_tool == "ConductResearch":
            chosen_tool_literal = "ConductResearch"
            tool_args = ConductResearch.model_validate(tool_args_raw).model_dump()
        elif chosen_tool == "Analyze":
            chosen_tool_literal = "Analyze"
            tool_args = Analyze.model_validate(tool_args_raw).model_dump()
        elif chosen_tool == "Write":
            chosen_tool_literal = "Write"
            tool_args = Write.model_validate(tool_args_raw).model_dump()
        else:
            chosen_tool_literal = "Finalize"
            tool_args = Finalize.model_validate(tool_args_raw).model_dump()
    except ValidationError:
        return None

    reasoning_summary_raw = content.get("reasoning_summary")
    if not isinstance(reasoning_summary_raw, str) or not reasoning_summary_raw.strip():
        return None

    now = _now_iso()
    outcome: Literal["dispatched", "succeeded"] = (
        "succeeded" if chosen_tool_literal == "Finalize" else "dispatched"
    )
    return SupervisorDecision(
        id=make_id("decision_"),
        run_id=run_id,
        iteration=iteration,
        chosen_tool=chosen_tool_literal,
        tool_args=tool_args,
        reasoning_summary=reasoning_summary_raw.strip(),
        triggered_by=triggered_by,
        outcome=outcome,
        outcome_recorded_at=now,
        created_at=now,
    )


async def _persist_iteration(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    iteration: int,
    decision: SupervisorDecision,
    llm_response: dict[str, Any],
) -> None:
    async with session_factory() as session:
        step = Step(
            step_id=make_id("step_"),
            run_id=run_id,
            agent_name="supervisor",
            status="running",
            retry_count=0,
            payload={
                "iteration": iteration,
                "chosen_tool": decision.chosen_tool,
                "tool_args": decision.tool_args,
                "llm_provider": llm_response.get("provider"),
                "llm_prompt_preview": llm_response.get("prompt_preview"),
            },
        )
        session.add(step)
        session.add(
            SupervisorDecisionRecord(
                id=decision.id,
                run_id=decision.run_id,
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


def _map_next_action(chosen_tool: str) -> Literal["researcher", "analyst", "writer", "finalize"]:
    if chosen_tool == "ConductResearch":
        return "researcher"
    if chosen_tool == "Analyze":
        return "analyst"
    if chosen_tool == "Write":
        return "writer"
    return "finalize"


async def supervisor_node(state: AgentState) -> AgentState:
    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("AgentState.session_factory is required for supervisor persistence.")

    run_id = state.get("run_id", make_id("run_"))
    decisions = list(state.get("decisions", []))
    user_query = state.get("user_query", "skeleton")
    competitors = list(state.get("competitors", []))
    researched_competitors = list(state.get("researched_competitors", []))
    analysis_done = bool(state.get("analysis_done", False))
    report_draft_done = bool(state.get("report_draft_done", False))
    qa_outcome = state.get("qa_outcome")
    qa_reject_to = state.get("qa_reject_to")
    qa_reasons = list(state.get("qa_reasons", []))
    iteration = int(state.get("current_iteration", 0)) + 1
    last_completed_node = state.get("last_completed_node")
    triggered_by = _resolve_triggered_by(
        iteration=iteration,
        last_completed_node=last_completed_node,
        qa_outcome=qa_outcome,
    )

    forced_degraded_by_qa = False
    qa_driven_decision = _decision_from_qa_feedback(
        run_id=run_id,
        iteration=iteration,
        triggered_by=triggered_by,
        qa_outcome=qa_outcome,
        qa_reject_to=qa_reject_to,
        qa_reasons=qa_reasons,
    )
    if qa_driven_decision is not None:
        decision, llm_response, forced_degraded_by_qa = qa_driven_decision
    elif iteration > MAX_SUPERVISOR_ITERATIONS:
        forced_now = _now_iso()
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Finalize",
            tool_args=Finalize(
                completion_reason="max_iterations_hit",
                notes="Supervisor reached max iterations and forced finalize.",
            ).model_dump(),
            reasoning_summary="Forced finalize due to supervisor max iteration guardrail.",
            triggered_by="iteration_advance",
            outcome="succeeded",
            outcome_recorded_at=forced_now,
            created_at=forced_now,
        )
        llm_response = {"provider": "guardrail", "prompt_preview": "max_iterations_hit"}
    else:
        llm_prompt = (
            f"user_query={user_query}\n"
            f"iteration={iteration}\n"
            f"competitors={competitors}\n"
            f"researched_competitors={researched_competitors}\n"
            f"analysis_done={analysis_done}\n"
            f"report_draft_done={report_draft_done}\n"
            "Return chosen_tool + tool_args + reasoning_summary."
        )
        llm_response = await llm_client.complete_json(prompt=llm_prompt, model_slot="research")
        decision = _try_llm_decision(
            run_id=run_id,
            iteration=iteration,
            llm_response=llm_response,
            triggered_by=triggered_by,
        )
        if decision is None:
            decision = _fallback_decision(
                run_id=run_id,
                iteration=iteration,
                competitors=competitors,
                researched_competitors=researched_competitors,
                analysis_done=analysis_done,
                report_draft_done=report_draft_done,
                triggered_by=triggered_by,
                user_query=user_query,
            )

    await _persist_iteration(
        session_factory=session_factory,
        run_id=run_id,
        iteration=iteration,
        decision=decision,
        llm_response=llm_response,
    )
    decisions.append(decision)

    next_action = _map_next_action(decision.chosen_tool)
    completion_reason = str(decision.tool_args.get("completion_reason", ""))
    if decision.chosen_tool == "Finalize":
        if completion_reason == "max_iterations_hit" or forced_degraded_by_qa:
            status = "degraded"
        else:
            status = "completed"
    else:
        status = "running"

    return {
        **state,
        "run_id": run_id,
        "decisions": decisions,
        "current_iteration": iteration,
        "pending_tool_args": decision.tool_args,
        "next_action": next_action,
        "last_completed_node": None,
        "researched_competitors": researched_competitors,
        "analysis_done": analysis_done,
        "report_draft_done": report_draft_done,
        "qa_outcome": None,
        "qa_reject_to": None,
        "qa_reasons": [],
        "status": status,
    }
