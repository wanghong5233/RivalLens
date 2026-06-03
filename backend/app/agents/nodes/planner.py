from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from db.engine import get_session_factory
from models.llm_call import LLMCall
from models.run import Run
from models.step import Step
from schemas.ids import make_id
from schemas.intake import RunIntakeDraft
from schemas.plan import PlanConfirmRequest, PlanTask, PlanTaskStage, PlanTree
from service.event_bus import RunEventType, emit_run_event
from service.llm import (
    PLANNER_SYSTEM_PROMPT,
    build_planner_fallback_user_prompt,
    build_planner_user_prompt,
)
from service.llm.client import get_llm_client
from service.llm.response import LLMResponse
from utils.log_node import log_node
from utils.logger import bind_step, get_logger

log = get_logger("agents.planner")

_VALID_STAGES: frozenset[str] = frozenset({"discover", "research", "analyze", "write"})
_MAX_RESEARCH_TASKS = 8
_MAX_TOTAL_TASKS = 12
_DEFAULT_FOCUS_DIMENSIONS: tuple[str, ...] = ("feature", "pricing", "user_feedback")
# Phase β: cap user-injected tasks. Backend defends; FE should also enforce so
# the validation message reaches the user before a round-trip.
_MAX_ADDITIONAL_TASKS = 5
# Phase β: user injections never include "discover" — that stage is the
# discovery node's exclusive output. Allowing it would let two discoveries
# compete and would also bypass `_derive_focus_dimensions`.
_USER_ALLOWED_STAGES: frozenset[str] = frozenset({"research", "analyze", "write"})


def _resolve_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _coerce_draft(state: AgentState) -> RunIntakeDraft:
    draft = state.get("intake_draft")
    if isinstance(draft, RunIntakeDraft):
        return draft
    if isinstance(draft, dict):
        return RunIntakeDraft.model_validate(draft)
    user_query = state.get("user_query") or ""
    return RunIntakeDraft(user_query=user_query)


def _coerce_pending_plan(state: AgentState) -> PlanTree:
    pending = state.get("pending_plan_tree")
    if isinstance(pending, PlanTree):
        return pending
    if isinstance(pending, dict):
        return PlanTree.model_validate(pending)
    raise RuntimeError(
        "planner_wait_node entered without pending_plan_tree in state; check graph wiring."
    )


def _normalize_focus_dimensions(values: object, draft_focus: list[str]) -> list[str]:
    if isinstance(values, list):
        cleaned = [str(v).strip() for v in values if isinstance(v, str) and v.strip()]
        if cleaned:
            return cleaned[:5]
    if draft_focus:
        return list(draft_focus)[:5]
    return list(_DEFAULT_FOCUS_DIMENSIONS)


def _parse_llm_tasks(
    raw_tasks: object, *, draft: RunIntakeDraft
) -> list[PlanTask] | None:
    """Return validated PlanTasks or None if the LLM output is unusable."""
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return None
    out: list[PlanTask] = []
    research_count = 0
    for item in raw_tasks:
        if not isinstance(item, dict):
            continue
        stage_raw = item.get("stage")
        if not isinstance(stage_raw, str) or stage_raw not in _VALID_STAGES:
            continue
        title_raw = item.get("title")
        if not isinstance(title_raw, str) or not title_raw.strip():
            continue
        description_raw = item.get("description")
        description = description_raw.strip() if isinstance(description_raw, str) else ""
        competitor_raw = item.get("competitor_id")
        competitor_id = (
            competitor_raw.strip()
            if isinstance(competitor_raw, str) and competitor_raw.strip()
            else None
        )
        if stage_raw == "research":
            if competitor_id is None:
                # Reject research tasks without competitor_id; planner_generate spec requires it.
                continue
            if research_count >= _MAX_RESEARCH_TASKS:
                continue
            research_count += 1
        focus = _normalize_focus_dimensions(
            item.get("focus_dimensions"), list(draft.focus_dimensions)
        )
        try:
            task = PlanTask(
                stage=cast(PlanTaskStage, stage_raw),
                title=title_raw.strip()[:60],
                description=description,
                competitor_id=competitor_id,
                focus_dimensions=focus,
                source="agent",
                enabled=True,
                priority="normal",
            )
        except ValidationError:
            continue
        out.append(task)
        if len(out) >= _MAX_TOTAL_TASKS:
            break
    if not out:
        return None
    return out


def _fallback_tasks(draft: RunIntakeDraft) -> list[PlanTask]:
    """Deterministic plan when the LLM output is unusable.

    Mirrors the supervisor's reachable execution path so the visible plan
    never lies about what the executor would do.
    """
    focus = list(draft.focus_dimensions) or list(_DEFAULT_FOCUS_DIMENSIONS)
    tasks: list[PlanTask] = []
    competitors = list(draft.competitors_explicit)
    if draft.competitors_discovery_mode or not competitors:
        tasks.append(
            PlanTask(
                stage="discover",
                title="发现赛道头部竞品",
                description="基于用户问题在公开渠道检索可能的头部竞品。",
                competitor_id=None,
                focus_dimensions=focus,
            )
        )
    for competitor in competitors[:_MAX_RESEARCH_TASKS]:
        tasks.append(
            PlanTask(
                stage="research",
                title=f"调研 {competitor}"[:60],
                description=f"按维度收集 {competitor} 的事实证据。",
                competitor_id=competitor,
                focus_dimensions=focus,
            )
        )
    tasks.append(
        PlanTask(
            stage="analyze",
            title="跨竞品对比分析",
            description="基于证据生成跨竞品对比与差异化洞察。",
            competitor_id=None,
            focus_dimensions=focus,
        )
    )
    tasks.append(
        PlanTask(
            stage="write",
            title="生成竞品分析报告",
            description="按用户角色和关注维度撰写报告。",
            competitor_id=None,
            focus_dimensions=focus,
        )
    )
    return tasks[:_MAX_TOTAL_TASKS]


def reconcile_plan_tree_after_discovery(
    *,
    plan_tree: PlanTree | dict[str, object],
    discovered_competitors: list[str],
    focus_dimensions: list[str] | None = None,
) -> PlanTree:
    """Materialize per-competitor research tasks after discovery completes."""
    plan = PlanTree.model_validate(plan_tree) if isinstance(plan_tree, dict) else plan_tree
    if not discovered_competitors:
        return plan

    existing_research = {
        task.competitor_id
        for task in plan.tasks
        if task.stage == "research" and isinstance(task.competitor_id, str) and task.competitor_id.strip()
    }

    focus = list(focus_dimensions or [])
    if not focus:
        for task in plan.tasks:
            if task.focus_dimensions:
                focus = list(task.focus_dimensions)
                break
    if not focus:
        focus = list(_DEFAULT_FOCUS_DIMENSIONS)

    insert_at = 0
    for index, task in enumerate(plan.tasks):
        if task.stage == "discover":
            insert_at = index + 1
    for index, task in enumerate(plan.tasks):
        if task.stage == "research":
            insert_at = index + 1

    new_research_tasks: list[PlanTask] = []
    for competitor in discovered_competitors[:_MAX_RESEARCH_TASKS]:
        if competitor in existing_research:
            continue
        new_research_tasks.append(
            PlanTask(
                stage="research",
                title=f"调研 {competitor}"[:60],
                description=f"按维度收集 {competitor} 的事实证据。",
                competitor_id=competitor,
                focus_dimensions=focus,
                source="agent",
                enabled=True,
            )
        )

    if not new_research_tasks:
        return plan

    tasks = list(plan.tasks)
    tasks[insert_at:insert_at] = new_research_tasks
    return plan.model_copy(update={"tasks": tasks, "version": plan.version + 1})


async def _persist_planner_step(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    action: str,
    plan: PlanTree,
    llm_response: LLMResponse,
    reasoning_summary: str,
) -> str:
    async with session_factory() as session:
        step = Step(
            step_id=make_id("step_"),
            run_id=run_id,
            agent_name="planner_agent",
            status="running",
            retry_count=0,
            payload={
                "phase": "planning",
                "action": action,
                "task_count": len(plan.tasks),
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "llm_provider": llm_response.provider,
                "llm_fallback_used": llm_response.fallback_used,
                "llm_fallback_reason": llm_response.fallback_reason,
                "reasoning_summary": reasoning_summary[:1000] if reasoning_summary else "",
            },
        )
        session.add(step)
        await session.flush()
        llm_call_error = (
            llm_response.error[:2000] if llm_response.error is not None else None
        )
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
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
        return step.step_id


def _normalize_user_tasks(additional_tasks: list[PlanTask]) -> list[PlanTask]:
    """Phase β: server-side hardening of `additional_tasks`.

    Rules (each violation drops the offending task — silent skip is *not* used;
    we raise so the FE surfaces the reason instead of producing a partial plan):
    - stage must be in {"research", "analyze", "write"}; "discover" is rejected.
    - research stage requires a non-empty `competitor_id`.
    - title must be non-empty after trim.
    - `task_id` is regenerated (client-supplied IDs are not trusted — would
      collide with planner ptask_ namespace).
    - `source` and `priority` are forced regardless of client payload.
    - `enabled` is forced True (a user-added task that is born disabled is
      contradictory; if they change their mind they can omit it instead).

    Caller enforces the count cap (`_MAX_ADDITIONAL_TASKS`).
    """
    normalized: list[PlanTask] = []
    for index, task in enumerate(additional_tasks):
        if task.stage not in _USER_ALLOWED_STAGES:
            raise ValueError(
                f"additional_tasks[{index}].stage={task.stage!r} is not user-addable "
                f"(allowed: {sorted(_USER_ALLOWED_STAGES)})"
            )
        title_trimmed = task.title.strip()
        if not title_trimmed:
            raise ValueError(f"additional_tasks[{index}].title must be non-empty")
        competitor_id = task.competitor_id.strip() if task.competitor_id else None
        if task.stage == "research":
            if not competitor_id:
                raise ValueError(
                    f"additional_tasks[{index}].competitor_id is required for stage=research"
                )
        normalized.append(
            PlanTask(
                task_id=make_id("ptask_"),
                stage=task.stage,
                title=title_trimmed[:60],
                description=task.description.strip()[:500],
                competitor_id=competitor_id if task.stage == "research" else None,
                focus_dimensions=list(task.focus_dimensions),
                source="user",
                enabled=True,
                priority="user_pinned",
            )
        )
    return normalized


async def _persist_plan_tree_to_run(*, run_id: str, plan: PlanTree) -> None:
    """Mirror the latest plan_tree onto the Run row.

    Same rationale as `_persist_intake_draft_to_run`: lets GET /api/runs/{id}
    render the plan without poking graph state.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.plan_tree = plan.model_dump()
        await session.commit()


@log_node("planner_generate")
async def planner_generate_node(state: AgentState) -> AgentState:
    """LLM-driven plan generation. Writes pending_plan_tree + emits plan.published.

    Invariant A: this is the *generate* half. All side effects (LLM call, Step+
    LLMCall persistence, Run.plan_tree mirror, PLAN_PUBLISHED event) commit
    before the wait node's interrupt(). Resumes only re-execute planner_wait.
    """
    session_factory = _resolve_session_factory(state)
    run_id = state.get("run_id") or make_id("run_")
    draft = _coerce_draft(state)

    user_prompt = build_planner_user_prompt(
        intake_draft=draft.model_dump(exclude={"is_complete"})
    )
    fallback_user_prompt = build_planner_fallback_user_prompt(
        intake_draft=draft.model_dump(exclude={"is_complete"})
    )
    llm_response = await get_llm_client().complete_json(
        model_slot="research",
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        fallback_system_prompt=PLANNER_SYSTEM_PROMPT,
        fallback_user_prompt=fallback_user_prompt,
    )

    content = llm_response.content if isinstance(llm_response.content, dict) else {}
    rationale_raw = content.get("rationale")
    rationale = rationale_raw.strip() if isinstance(rationale_raw, str) else ""

    parsed_tasks = _parse_llm_tasks(content.get("tasks"), draft=draft)
    if parsed_tasks is None:
        tasks = _fallback_tasks(draft)
        action = "publish_fallback"
    else:
        tasks = parsed_tasks
        action = "publish"

    plan = PlanTree(tasks=tasks, rationale=rationale, version=1, confirmed_at=None)

    step_id = await _persist_planner_step(
        session_factory=session_factory,
        run_id=run_id,
        action=action,
        plan=plan,
        llm_response=llm_response,
        reasoning_summary=rationale,
    )
    await _persist_plan_tree_to_run(run_id=run_id, plan=plan)

    with bind_step(step_id):
        log.info(
            "planner.publish",
            run_id=run_id,
            task_count=len(plan.tasks),
            action=action,
            llm_provider=llm_response.provider,
            llm_fallback_used=llm_response.fallback_used,
        )

    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.PLAN_PUBLISHED,
        step_id=step_id,
        payload={
            "plan_id": plan.plan_id,
            "task_count": len(plan.tasks),
            "version": plan.version,
            "plan_tree": plan.model_dump(),
        },
    )

    # Seed state.competitors from the intake's explicit list so the supervisor's
    # hard-constraint guard (discovery_needed = len(competitors)==0) sees them.
    # Without this seed the supervisor forces DiscoverCompetitors even when the
    # user already named the competitors during intake. operator.add appends, so
    # we filter out anything already present and only return the diff.
    state_dict = cast(dict[str, Any], state)
    existing_competitors = list(state_dict.get("competitors") or [])
    competitors_seed: list[str] = []
    if not draft.competitors_discovery_mode and draft.competitors_explicit:
        seen = set(existing_competitors)
        for competitor in draft.competitors_explicit:
            if competitor in seen:
                continue
            seen.add(competitor)
            competitors_seed.append(competitor)

    state_without_competitors = {
        key: value for key, value in state_dict.items() if key != "competitors"
    }
    result: dict[str, Any] = {
        **state_without_competitors,
        "run_id": run_id,
        "phase": "planning",
        "pending_plan_tree": plan,
    }
    if competitors_seed:
        result["competitors"] = competitors_seed
    return result


@log_node("planner_wait")
async def planner_wait_node(state: AgentState) -> AgentState:
    """Pure interrupt node. Idempotent: on replay it just re-issues interrupt().

    Invariant A: no LLM calls, no DB writes before interrupt(). All side effects
    after interrupt() run exactly once per resume.

    Phase β: honors `disabled_task_ids` against pending plan tasks AND merges
    `additional_tasks` (forced source="user", priority="user_pinned") onto the
    end of the kept list. User-pinned research competitors that aren't yet in
    `state.competitors` are returned as a diff so the supervisor can skip the
    discovery round-trip and target them directly.
    """
    pending = _coerce_pending_plan(state)
    raw_confirm: Any = interrupt(
        {"kind": "plan_confirm", "plan_tree": pending.model_dump()}
    )

    try:
        confirm = PlanConfirmRequest.model_validate(raw_confirm)
    except ValidationError as exc:
        # Same fail-fast contract as intake_wait: the resume endpoint is the
        # sole writer of resume values and must validate before Command(resume=).
        raise RuntimeError(
            f"planner_wait resume value failed validation: {exc}"
        ) from exc

    if len(confirm.additional_tasks) > _MAX_ADDITIONAL_TASKS:
        raise RuntimeError(
            f"additional_tasks count ({len(confirm.additional_tasks)}) "
            f"exceeds limit ({_MAX_ADDITIONAL_TASKS})"
        )
    try:
        user_tasks = _normalize_user_tasks(confirm.additional_tasks)
    except ValueError as exc:
        raise RuntimeError(f"additional_tasks validation failed: {exc}") from exc

    disabled = set(confirm.disabled_task_ids)
    pending_task_ids = {task.task_id for task in pending.tasks}
    unknown_disabled = [tid for tid in disabled if tid not in pending_task_ids]
    if unknown_disabled:
        # FE may race against a stale plan version. Surface the mismatch
        # instead of silently dropping the unknown IDs.
        raise RuntimeError(
            f"disabled_task_ids reference non-existent tasks: {sorted(unknown_disabled)}"
        )

    kept_tasks = [task for task in pending.tasks if task.task_id not in disabled]
    merged_tasks = kept_tasks + user_tasks
    confirmed = PlanTree(
        plan_id=pending.plan_id,
        tasks=merged_tasks,
        rationale=pending.rationale,
        version=pending.version + 1,
        confirmed_at=datetime.now(timezone.utc).isoformat(),
    )

    run_id = state.get("run_id") or make_id("run_")
    await _persist_plan_tree_to_run(run_id=run_id, plan=confirmed)

    # User-injected research competitors must be added to state.competitors so
    # the supervisor's hard-constraint guard accepts them. operator.add
    # concatenates onto current state — we only return the *diff* (new IDs)
    # to avoid duplicates.
    existing_competitors = set(state.get("competitors", []) or [])
    new_user_competitors = [
        task.competitor_id
        for task in user_tasks
        if task.stage == "research"
        and task.competitor_id is not None
        and task.competitor_id not in existing_competitors
    ]
    # De-dup the diff itself (user could have added the same competitor twice).
    seen_diff: set[str] = set()
    competitors_diff: list[str] = []
    for competitor in new_user_competitors:
        if competitor in seen_diff:
            continue
        seen_diff.add(competitor)
        competitors_diff.append(competitor)

    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.PLAN_CONFIRMED,
        step_id=None,
        payload={
            "plan_id": confirmed.plan_id,
            "version": confirmed.version,
            "kept_task_count": len(kept_tasks),
            "user_task_count": len(user_tasks),
            "disabled_task_ids": sorted(disabled),
            "confirmed_at": confirmed.confirmed_at,
        },
    )

    state_dict = cast(dict[str, Any], state)
    # `**state` would spread `competitors` from the current snapshot, but
    # LangGraph's operator.add reducer would then concat `competitors_diff`
    # on top. We don't want the existing list duplicated, so we omit it
    # from the spread when there's a diff to add — the reducer keeps the
    # existing state.competitors intact and only the diff is appended.
    state_without_competitors = {
        key: value for key, value in state_dict.items() if key != "competitors"
    }
    result: dict[str, Any] = {
        **state_without_competitors,
        "run_id": run_id,
        "phase": "executing",
        "plan_tree": confirmed,
        "pending_plan_tree": None,
    }
    if competitors_diff:
        result["competitors"] = competitors_diff
    return result
