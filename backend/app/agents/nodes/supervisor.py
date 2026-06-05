from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from core.defaults import (
    DEFAULT_FOCUS_DIMENSIONS,
    MAX_RESEARCH_COMPETITORS,
    MAX_WRITE_SECTIONS,
)
from db.engine import get_session_factory
from models.llm_call import LLMCall
from models.run import Run
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from service.llm import (
    SUPERVISOR_SYSTEM_PROMPT,
    build_supervisor_fallback_user_prompt,
    build_supervisor_repair_user_prompt,
    build_supervisor_user_prompt,
)
from service.llm.harness import complete_structured
from service.llm.response import LLMResponse
from utils.log_node import log_node
from utils.logger import bind_step, get_logger

log = get_logger("agents.supervisor")
from schemas.agent_outputs import SupervisorToolCallOutput
from schemas.ids import make_id
from schemas.supervisor import (
    Analyze,
    ConductResearch,
    ConductResearchBatch,
    DiscoverCompetitors,
    Finalize,
    SupervisorDecision,
    Write,
)
from service.event_bus import RunEventType, emit_run_event

MAX_SUPERVISOR_ITERATIONS = 10
DIMENSION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pricing", ("pricing", "price", "cost", "套餐", "定价", "收费")),
    ("user_feedback", ("review", "feedback", "rating", "评价", "口碑", "用户声音")),
    ("feature", ("feature", "capability", "功能", "能力", "workflow")),
    ("positioning", ("positioning", "market", "segment", "定位", "市场")),
    ("tech_stack", ("integration", "api", "architecture", "tech", "技术", "集成")),
    ("go_to_market", ("growth", "distribution", "channel", "营销", "获客")),
)
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


def _stable_unique(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _derive_focus_dimensions(*, user_query: str, competitors: list[str]) -> list[str]:
    normalized_query = user_query.lower()
    derived: list[str] = []
    for dimension, hints in DIMENSION_HINTS:
        if any(hint in normalized_query for hint in hints):
            derived.append(dimension)

    if not derived:
        derived.extend(DEFAULT_FOCUS_DIMENSIONS)
    if len(competitors) >= 3 and "positioning" not in derived:
        derived.append("positioning")
    if len(derived) < 3:
        derived.extend(DEFAULT_FOCUS_DIMENSIONS)
    return _stable_unique(derived)[:5]


def _derive_write_sections(*, focus_dimensions: list[str]) -> list[str]:
    sections = _stable_unique([*focus_dimensions, "differentiation"])
    return sections[:MAX_WRITE_SECTIONS]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _pseudo_llm_response(
    *,
    provider: str,
    model_name: str,
    prompt_preview: str,
    error: str | None,
) -> LLMResponse:
    return LLMResponse(
        model_slot="research",
        provider=provider,
        model_name=model_name,
        prompt_preview=prompt_preview,
        prompt_hash="pseudo_response",
        content={},
        prompt_tokens=None,
        completion_tokens=None,
        latency_ms=0,
        error=error,
    )


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
    now = _now_iso()

    if not competitors:
        args = DiscoverCompetitors(
            search_queries=[user_query, f"{user_query} competitors alternatives"],
            domain_context=user_query,
            max_results=8,
        ).model_dump()
        return SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="DiscoverCompetitors",
            tool_args=args,
            reasoning_summary="No competitors provided; fallback triggers discovery phase.",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )

    pending_competitors = [c for c in competitors if c not in researched_competitors]
    fallback_dimensions = _derive_focus_dimensions(user_query=user_query, competitors=competitors)
    fallback_sections = _derive_write_sections(focus_dimensions=fallback_dimensions)
    now = _now_iso()

    if len(pending_competitors) >= 2:
        topics = [
            ConductResearch(
                research_topic=f"{competitor_id} vs user_query={user_query}",
                competitor_id=competitor_id,
                focus_dimensions=fallback_dimensions,
                max_iterations=6,
                fallback_to_offline=True,
            )
            for competitor_id in pending_competitors[:MAX_RESEARCH_COMPETITORS]
        ]
        args = ConductResearchBatch(
            topics=topics,
            parallelism_rationale=(
                f"Fallback planner batches {len(topics)} pending competitors to reduce wall-clock time."
            ),
        ).model_dump()
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="ConductResearchBatch",
            tool_args=args,
            reasoning_summary=(
                f"Fallback planner dispatches {len(topics)} pending competitors in parallel research."
            ),
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return decision

    if len(pending_competitors) == 1:
        competitor_id = pending_competitors[0]
        args = ConductResearch(
            research_topic=f"{competitor_id} vs user_query={user_query}",
            competitor_id=competitor_id,
            focus_dimensions=fallback_dimensions,
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
            focus_dimensions=fallback_dimensions,
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
            template_id=None,
            sections=fallback_sections,
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
    user_query: str,
    competitors: list[str],
    fallback_dimensions: list[str],
    fallback_sections: list[str],
) -> tuple[SupervisorDecision, LLMResponse, bool] | None:
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
            _pseudo_llm_response(
                provider="qa_guardrail",
                model_name="qa_guardrail",
                prompt_preview="qa_force_degraded",
                error="qa_force_degraded",
            ),
            True,
        )

    if qa_reject_to == "supervisor":
        # Let the planner decide next action with full context instead of forcing degraded finalize.
        return None

    if qa_reject_to == "writer":
        qa_reason_summary = "; ".join(qa_reasons[:3]) or "QA blocking rules failed."
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Write",
            tool_args=Write(
                template_id=None,
                sections=fallback_sections,
            ).model_dump(),
            reasoning_summary=f"QA rejected writer output and requests rewrite: {qa_reason_summary}",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return (
            decision,
            _pseudo_llm_response(
                provider="qa_guardrail",
                model_name="qa_guardrail",
                prompt_preview="qa_rejected_to_writer",
                error=None,
            ),
            False,
        )

    if qa_reject_to == "analyst":
        qa_reason_summary = "; ".join(qa_reasons[:3]) or "QA requests deeper analysis."
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool="Analyze",
            tool_args=Analyze(
                focus_dimensions=fallback_dimensions,
                parallel_by_dimension=True,
                require_cross_competitor=True,
            ).model_dump(),
            reasoning_summary=(
                "QA rejected current report and requests analyst re-check: "
                f"{qa_reason_summary}"
            ),
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return (
            decision,
            _pseudo_llm_response(
                provider="qa_guardrail",
                model_name="qa_guardrail",
                prompt_preview="qa_rejected_to_analyst",
                error=None,
            ),
            False,
        )

    if qa_reject_to == "researcher":
        qa_reason_summary = "; ".join(qa_reasons[:3]) or "QA requests additional evidence."
        topics = [
            ConductResearch(
                research_topic=(
                    "Collect additional evidence to address QA findings for "
                    f"{competitor_id} on query: {user_query}"
                ),
                competitor_id=competitor_id,
                focus_dimensions=fallback_dimensions,
                max_iterations=3,
                fallback_to_offline=True,
            )
            for competitor_id in competitors[:MAX_RESEARCH_COMPETITORS]
        ]
        if not topics:
            return None
        if len(topics) == 1:
            chosen_tool: Literal["ConductResearch", "ConductResearchBatch"] = "ConductResearch"
            tool_args = topics[0].model_dump()
        else:
            chosen_tool = "ConductResearchBatch"
            tool_args = ConductResearchBatch(
                topics=topics,
                parallelism_rationale=(
                    "QA requested additional evidence, rerun research across competitors in parallel."
                ),
            ).model_dump()
        decision = SupervisorDecision(
            id=make_id("decision_"),
            run_id=run_id,
            iteration=iteration,
            chosen_tool=chosen_tool,
            tool_args=tool_args,
            reasoning_summary=f"QA requires additional research evidence: {qa_reason_summary}",
            triggered_by=triggered_by,
            outcome="dispatched",
            outcome_recorded_at=now,
            created_at=now,
        )
        return (
            decision,
            _pseudo_llm_response(
                provider="qa_guardrail",
                model_name="qa_guardrail",
                prompt_preview="qa_rejected_to_researcher",
                error=None,
            ),
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
        _pseudo_llm_response(
            provider="qa_guardrail",
            model_name="qa_guardrail",
            prompt_preview="qa_rejected_unimplemented_target",
            error="qa_rejected_unimplemented_target",
        ),
        True,
    )


def _decision_from_tool_output(
    *,
    run_id: str,
    iteration: int,
    output: SupervisorToolCallOutput,
    triggered_by: TriggerSource,
) -> SupervisorDecision:
    now = _now_iso()
    outcome: Literal["dispatched", "succeeded"] = (
        "succeeded" if output.chosen_tool == "Finalize" else "dispatched"
    )
    return SupervisorDecision(
        id=make_id("decision_"),
        run_id=run_id,
        iteration=iteration,
        chosen_tool=output.chosen_tool,
        tool_args=output.tool_args,
        reasoning_summary=output.reasoning_summary,
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
    llm_response: LLMResponse,
) -> str:
    async with session_factory() as session:
        llm_call_error = llm_response.error[:2000] if llm_response.error is not None else None
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
                "llm_provider": llm_response.provider,
                "llm_prompt_preview": llm_response.prompt_preview,
                "llm_fallback_used": llm_response.fallback_used,
                "llm_fallback_reason": llm_response.fallback_reason,
            },
        )
        session.add(step)
        await session.flush()
        session.add(
            LLMCall(
                step_id=step.step_id,
                model_slot=llm_response.model_slot,
                provider=llm_response.provider,
                model_name=llm_response.model_name,
                prompt_hash=llm_response.prompt_hash,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                latency_ms=llm_response.latency_ms,
                error=llm_call_error,
            )
        )
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
    return step.step_id


def _extract_user_pinned_research(
    *,
    plan_tree: object,
    researched_competitors: list[str],
) -> list[dict[str, object]]:
    """Phase β: project user-injected research tasks that are still pending.

    Returns a list of {competitor_id, title, focus_dimensions} dicts the
    supervisor prompt builder turns into a "user pinned" hint section. Filters
    out competitors that already appear in `researched_competitors` so we
    don't nag the LLM about work it's already done.
    """
    if not isinstance(plan_tree, dict):
        return []
    tasks_raw = plan_tree.get("tasks")
    if not isinstance(tasks_raw, list):
        return []
    done = set(researched_competitors)
    pinned: list[dict[str, object]] = []
    for task in tasks_raw:
        if not isinstance(task, dict):
            continue
        if task.get("source") != "user":
            continue
        if task.get("priority") != "user_pinned":
            continue
        if task.get("stage") != "research":
            continue
        if task.get("enabled") is False:
            continue
        competitor_id = task.get("competitor_id")
        if not isinstance(competitor_id, str) or not competitor_id.strip():
            continue
        if competitor_id in done:
            continue
        title_raw = task.get("title")
        focus_raw = task.get("focus_dimensions")
        pinned.append(
            {
                "competitor_id": competitor_id,
                "title": title_raw if isinstance(title_raw, str) else "",
                "focus_dimensions": (
                    [f for f in focus_raw if isinstance(f, str)]
                    if isinstance(focus_raw, list)
                    else []
                ),
            }
        )
    return pinned


async def _load_pending_follow_ups(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> list[dict[str, object]]:
    """Phase 4: read FollowUpEntry rows with consumed_at=None from Run.follow_ups.

    Returns plain dicts (not Pydantic models) — the supervisor prompt builder
    only needs `id` / `text` / `applies_to_stage`, and round-tripping through
    FollowUpEntry would discard fields the FE may add later.
    """
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None or run.follow_ups is None:
            return []
        pending: list[dict[str, object]] = []
        for entry in run.follow_ups:
            if not isinstance(entry, dict):
                continue
            if entry.get("consumed_at") is None:
                pending.append(entry)
    return pending


async def _mark_follow_ups_consumed(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    follow_up_ids: list[str],
    iteration: int,
) -> None:
    """Phase 4: stamp `consumed_at` + `consumed_in_iteration` on the listed IDs.

    Reads + writes inside one session so we don't race with a concurrent
    POST /follow-up. Unknown IDs are silently skipped (defensive — the
    endpoint never reuses fu_ ids so this should never happen).
    """
    if not follow_up_ids:
        return
    target_ids = set(follow_up_ids)
    consumed_at = _now_iso()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None or run.follow_ups is None:
            return
        updated: list[dict[str, object]] = []
        changed = False
        for entry in run.follow_ups:
            if not isinstance(entry, dict):
                updated.append(entry)
                continue
            entry_id = entry.get("id")
            if (
                isinstance(entry_id, str)
                and entry_id in target_ids
                and entry.get("consumed_at") is None
            ):
                new_entry = {
                    **entry,
                    "consumed_at": consumed_at,
                    "consumed_in_iteration": iteration,
                }
                updated.append(new_entry)
                changed = True
            else:
                updated.append(entry)
        if changed:
            run.follow_ups = updated
            await session.commit()


def _map_next_action(chosen_tool: str) -> Literal["discovery", "researcher", "analyst", "writer", "finalize"]:
    if chosen_tool == "DiscoverCompetitors":
        return "discovery"
    if chosen_tool in {"ConductResearch", "ConductResearchBatch"}:
        return "researcher"
    if chosen_tool == "Analyze":
        return "analyst"
    if chosen_tool == "Write":
        return "writer"
    return "finalize"


_CHOSEN_TOOL_TO_PLAN_STAGE: dict[str, str] = {
    "DiscoverCompetitors": "discover",
    "ConductResearch": "research",
    "ConductResearchBatch": "research",
    "Analyze": "analyze",
    "Write": "write",
}


def _match_plan_task_ids(
    *,
    plan_tree: object,
    decision: SupervisorDecision,
) -> list[str]:
    """Best-effort map supervisor decision → plan_task IDs for the live plan tree.

    Returns empty list when:
    - plan_tree is missing / unconfirmed (legacy runs, intake-skip, Finalize),
    - or no task in plan_tree matches the chosen tool + competitor(s).
    The FE uses this list to flip task tiles to "running"; a miss is harmless.
    """
    if not isinstance(plan_tree, dict):
        return []
    tasks_raw = plan_tree.get("tasks")
    if not isinstance(tasks_raw, list):
        return []
    target_stage = _CHOSEN_TOOL_TO_PLAN_STAGE.get(decision.chosen_tool)
    if target_stage is None:
        return []

    target_competitor_ids: set[str] = set()
    if decision.chosen_tool == "ConductResearch":
        competitor_id_raw = decision.tool_args.get("competitor_id")
        if isinstance(competitor_id_raw, str) and competitor_id_raw:
            target_competitor_ids.add(competitor_id_raw)
    elif decision.chosen_tool == "ConductResearchBatch":
        topics_raw = decision.tool_args.get("topics")
        if isinstance(topics_raw, list):
            for topic in topics_raw:
                if isinstance(topic, dict):
                    competitor_id_raw = topic.get("competitor_id")
                    if isinstance(competitor_id_raw, str) and competitor_id_raw:
                        target_competitor_ids.add(competitor_id_raw)

    matched: list[str] = []
    for task in tasks_raw:
        if not isinstance(task, dict):
            continue
        if task.get("stage") != target_stage:
            continue
        if target_stage == "research":
            task_competitor = task.get("competitor_id")
            if not isinstance(task_competitor, str) or task_competitor not in target_competitor_ids:
                continue
        task_id_raw = task.get("task_id")
        if isinstance(task_id_raw, str) and task_id_raw:
            matched.append(task_id_raw)
    return matched


@log_node("supervisor")
async def supervisor_node(state: AgentState) -> AgentState:
    session_factory = _resolve_session_factory(state)

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
    fallback_dimensions = _derive_focus_dimensions(
        user_query=user_query,
        competitors=competitors,
    )
    fallback_sections = _derive_write_sections(
        focus_dimensions=fallback_dimensions,
    )

    # Pre-declared so the mark-consumed call after persist is unconditional;
    # only the LLM branch overwrites it (qa-driven + max-iter branches don't
    # actually present the follow-ups to any LLM, so we leave them pending).
    pending_follow_ups: list[dict[str, object]] = []

    forced_degraded_by_qa = False
    qa_driven_decision = _decision_from_qa_feedback(
        run_id=run_id,
        iteration=iteration,
        triggered_by=triggered_by,
        qa_outcome=qa_outcome,
        qa_reject_to=qa_reject_to,
        qa_reasons=qa_reasons,
        user_query=user_query,
        competitors=competitors,
        fallback_dimensions=fallback_dimensions,
        fallback_sections=fallback_sections,
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
        llm_response = _pseudo_llm_response(
            provider="guardrail",
            model_name="guardrail",
            prompt_preview="max_iterations_hit",
            error="max_iterations_hit",
        )
    else:
        pending_follow_ups = await _load_pending_follow_ups(
            session_factory=session_factory,
            run_id=run_id,
        )
        user_pinned_research = _extract_user_pinned_research(
            plan_tree=state.get("plan_tree"),
            researched_competitors=researched_competitors,
        )
        user_prompt = build_supervisor_user_prompt(
            user_query=user_query,
            iteration=iteration,
            competitors=competitors,
            researched_competitors=researched_competitors,
            analysis_done=analysis_done,
            report_draft_done=report_draft_done,
            qa_outcome=qa_outcome,
            qa_reject_to=qa_reject_to,
            qa_reasons=qa_reasons,
            pending_follow_ups=pending_follow_ups,
            user_pinned_research=user_pinned_research,
        )
        fallback_user_prompt = build_supervisor_fallback_user_prompt(
            user_query=user_query,
            competitors=competitors,
            researched_competitors=researched_competitors,
            analysis_done=analysis_done,
            report_draft_done=report_draft_done,
            pending_follow_ups=pending_follow_ups,
            user_pinned_research=user_pinned_research,
        )
        harness_result = await complete_structured(
            model_slot="research",
            system_prompt=SUPERVISOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=SupervisorToolCallOutput,
            parser=SupervisorToolCallOutput.parse_llm_content,
            fallback_system_prompt=SUPERVISOR_SYSTEM_PROMPT,
            fallback_user_prompt=fallback_user_prompt,
            repair_user_prompt_builder=lambda errors: build_supervisor_repair_user_prompt(
                validation_errors=errors,
                user_query=user_query,
                iteration=iteration,
                competitors=competitors,
            ),
            log_event="supervisor.harness.finish",
        )
        llm_response = harness_result.llm_response
        if harness_result.value is not None:
            decision = _decision_from_tool_output(
                run_id=run_id,
                iteration=iteration,
                output=harness_result.value,
                triggered_by=triggered_by,
            )
        else:
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

    persisted_step_id = await _persist_iteration(
        session_factory=session_factory,
        run_id=run_id,
        iteration=iteration,
        decision=decision,
        llm_response=llm_response,
    )
    consumed_follow_up_ids: list[str] = []
    for entry in pending_follow_ups:
        entry_id = entry.get("id")
        if isinstance(entry_id, str) and entry_id:
            consumed_follow_up_ids.append(entry_id)
    if consumed_follow_up_ids:
        await _mark_follow_ups_consumed(
            session_factory=session_factory,
            run_id=run_id,
            follow_up_ids=consumed_follow_up_ids,
            iteration=iteration,
        )
    with bind_step(persisted_step_id):
        log.info(
            "supervisor.decision",
            iteration=iteration,
            chosen_tool=decision.chosen_tool,
            triggered_by=decision.triggered_by,
            outcome=decision.outcome,
            reasoning_summary_len=len(decision.reasoning_summary),
            tool_arg_keys=sorted(decision.tool_args.keys()),
        )
    plan_task_ids = _match_plan_task_ids(
        plan_tree=state.get("plan_tree"),
        decision=decision,
    )
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.SUPERVISOR_DECISION,
        step_id=persisted_step_id,
        payload={
            "iteration": iteration,
            "chosen_tool": decision.chosen_tool,
            "triggered_by": decision.triggered_by or "unknown",
            "outcome": decision.outcome or "unknown",
            "plan_task_ids": plan_task_ids,
            "consumed_follow_up_ids": consumed_follow_up_ids,
        },
    )
    decisions.append(decision)

    next_action = _map_next_action(decision.chosen_tool)
    completion_reason = str(decision.tool_args.get("completion_reason", ""))
    next_analysis_done = analysis_done
    next_report_draft_done = report_draft_done
    if decision.chosen_tool in {"ConductResearch", "ConductResearchBatch"}:
        # Fresh research invalidates prior downstream artifacts; force analysis+write rerun.
        next_analysis_done = False
        next_report_draft_done = False
    elif decision.chosen_tool == "Analyze":
        # Re-analysis requires a fresh writer pass before finalize.
        next_report_draft_done = False

    if decision.chosen_tool == "Finalize":
        writer_fallback = bool(state.get("writer_report_fallback_mode"))
        if (
            completion_reason == "max_iterations_hit"
            or forced_degraded_by_qa
            or writer_fallback
        ):
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
        "analysis_done": next_analysis_done,
        "report_draft_done": next_report_draft_done,
        "qa_outcome": None,
        "qa_reject_to": None,
        "qa_reasons": [],
        "status": status,
    }
