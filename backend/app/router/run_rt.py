from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Awaitable, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import yaml

from core.defaults import DEFAULT_FOCUS_DIMENSIONS
from db.engine import get_session_factory
from core.config import settings
from exceptions.base import APIException
from models.conclusion import ConclusionRecord
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.report import Report
from models.run import Run
from models.run_create_request import RunCreateRequestRecord
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from models.watchlist import WatchlistItem
from schemas.ids import make_id
from schemas.intake import IntakeClarifyRequest, IntakeUserReply, RunIntakeDraft, UserRole
from schemas.plan import FollowUpEntry, FollowUpRequest, PlanConfirmRequest
from service.conclusion import load_conclusions_for_run
from service.event_bus import EventBus, RunEventType, emit_run_event
from service.metrics import RunMetricsSnapshot, build_run_metrics_snapshot
from service.skill_curator.tasks import run_skill_curator_for_run
from utils.logger import bind_run, format_exception_for_log, get_logger

router = APIRouter()
log = get_logger("router.run_rt")

_RUN_PROGRESS_INTERVAL_SECONDS = 180


async def _run_graph_with_progress_heartbeat(
    *,
    run_id: str,
    phase: str,
    graph: Any,
    config: dict[str, object],
    invoke_coro: Awaitable[Any],
) -> Any:
    """Emit structlog heartbeats while a long graph.ainvoke is in flight."""
    started_at = datetime.now(timezone.utc)
    stop_event = asyncio.Event()

    async def _heartbeat_loop() -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_RUN_PROGRESS_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                checkpoint_next: str | None = None
                try:
                    snapshot = await graph.aget_state(config)
                    if snapshot.next:
                        checkpoint_next = str(snapshot.next[0])
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    checkpoint_next = None
                log.debug(
                    "run.progress",
                    run_id=run_id,
                    phase=phase,
                    elapsed_ms=int(
                        (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
                    ),
                    checkpoint_next=checkpoint_next,
                )

    heartbeat_task = asyncio.create_task(_heartbeat_loop(), name=f"run_progress_{run_id}")
    try:
        return await invoke_coro
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task

ResetToStage = Literal["analyst", "writer"]
RESETTABLE_RUN_STATUS = {"completed", "degraded"}
RESET_STAGE_AGENT_NAMES: dict[ResetToStage, tuple[str, ...]] = {
    "writer": ("writer", "qa", "skill_curator"),
    "analyst": ("analyst", "writer", "qa", "skill_curator"),
}
RESET_STAGE_DECISION_TOOLS: dict[ResetToStage, tuple[str, ...]] = {
    "writer": ("Write", "Finalize"),
    "analyst": ("Analyze", "Write", "Finalize"),
}


class RunCreateRequest(BaseModel):
    user_query: str = "skeleton"
    competitors: list[str] = Field(default_factory=list)
    domain_hint: str | None = None
    reference_urls: list[str] | None = None
    target_roles: list[str] = Field(default_factory=list)

    @field_validator("domain_hint")
    @classmethod
    def _normalize_domain_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @field_validator("reference_urls")
    @classmethod
    def _normalize_reference_urls(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized


class RunCreateResponse(BaseModel):
    run_id: str
    status: str
    message: str


class IntakeCreateRequest(BaseModel):
    """Body for POST /api/runs/intake.

    Chat mode (default): only `user_query` (+ optional `user_role`) is expected; the
    Agent clarifies the rest. Expert mode (`?mode=expert`): the caller pre-fills the
    full draft and the Agent skips clarification.
    """

    user_query: str
    user_role: UserRole | None = None
    domain_hint: str | None = None
    reference_urls: list[str] | None = None
    competitors_explicit: list[str] = Field(default_factory=list)
    competitors_discovery_mode: bool = False
    focus_dimensions: list[str] = Field(default_factory=list)
    report_depth: Literal["quick", "deep"] = "quick"
    client_request_id: str | None = None

    @field_validator("client_request_id")
    @classmethod
    def _normalize_client_request_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class IntakeCreateResponse(BaseModel):
    run_id: str
    status: str
    phase: str
    intake_draft: RunIntakeDraft
    # Async create contract: first clarify arrives via SSE. Keep this optional field
    # for backward-compatibility with older clients that still read it.
    first_clarify_request: IntakeClarifyRequest | None = None


class RunAcceptedResponse(BaseModel):
    """Async-accept envelope for all resume endpoints (Invariant C)."""

    run_id: str
    status: str


class FollowUpAcceptedResponse(BaseModel):
    """Phase 4: POST /follow-up response. `follow_up_id` lets the FE display
    the entry in any "pending instructions" UI before the supervisor consumes it.
    """

    run_id: str
    follow_up_id: str
    received_at: str


class RunResetRequest(BaseModel):
    reset_to: ResetToStage


class RunDetailResponse(BaseModel):
    run_id: str
    user_query: str
    # LLM-generated short label populated at intake.complete. Nullable for
    # legacy runs and brief intake-only window; FE falls back to truncating
    # user_query when this is null.
    title: str | None = None
    domain_hint: str | None
    reference_urls: list[str]
    status: str
    target_roles: list[str]
    competitors: list[str]
    started_at: str
    finished_at: str | None
    created_at: str
    # Phase 1b additions: derived from status + intake_draft + plan_tree so the FE
    # can render the live-run page without re-reading the LangGraph checkpoint.
    phase: Literal["intake", "planning", "executing", "done"] | None = None
    intake_draft: dict[str, object] | None = None
    plan_tree: dict[str, object] | None = None


class RunListItemResponse(BaseModel):
    run_id: str
    user_query: str
    title: str | None = None
    domain_hint: str | None
    status: str
    started_at: str
    finished_at: str | None
    created_at: str
    step_count: int
    evidence_count: int
    has_report: bool


class RunListResponse(BaseModel):
    items: list[RunListItemResponse]
    total: int
    limit: int
    offset: int


class StepTraceResponse(BaseModel):
    step_id: str
    run_id: str
    agent_name: str
    status: str
    retry_count: int
    payload: dict[str, object]
    started_at: str
    finished_at: str | None
    created_at: str


class SupervisorDecisionTraceResponse(BaseModel):
    id: str
    run_id: str
    iteration: int
    chosen_tool: str
    tool_args: dict[str, object]
    reasoning_summary: str
    triggered_by: str | None
    outcome: str | None
    outcome_recorded_at: str | None
    created_at: str


class LLMCallTraceResponse(BaseModel):
    id: int
    step_id: str
    model_slot: str
    provider: str | None
    model_name: str | None
    prompt_hash: str | None
    prompt_preview: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    error: str | None
    fallback_used: bool | None
    fallback_reason: str | None
    created_at: str


class TraceTimelineItemResponse(BaseModel):
    kind: Literal["step", "decision", "llm_call"]
    timestamp: str
    step_id: str | None
    agent_name: str | None
    summary: str
    payload: dict[str, object]


class RunTraceResponse(BaseModel):
    run: RunDetailResponse
    steps: list[StepTraceResponse]
    supervisor_decisions: list[SupervisorDecisionTraceResponse]
    llm_calls: list[LLMCallTraceResponse]
    timeline: list[TraceTimelineItemResponse]


class EvidenceBriefResponse(BaseModel):
    evidence_id: str
    source_type: str
    source_url: str | None
    source_title: str | None
    competitor_id: str | None


class RunReportResponse(BaseModel):
    run_id: str
    status: str
    content_markdown: str
    content_json: dict[str, object]
    generated_at: str
    evidence_id_to_brief: dict[str, EvidenceBriefResponse]


class EvidenceListItemResponse(BaseModel):
    evidence_id: str
    run_id: str
    source_type: str
    source_url: str | None
    source_title: str | None
    sanitized_text: str
    competitor_id: str | None
    metadata: dict[str, object] | None
    collected_at: str
    created_at: str


class CompetitorSeedResponse(BaseModel):
    id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    official_url: str | None = None
    category: str | None = None


class RunMetricsResponse(BaseModel):
    run_id: str
    coverage_rate: float
    evidence_count_total: int
    evidence_count_by_competitor: dict[str, int]
    source_type_distribution: dict[str, int]
    desensitization_coverage: float
    qa_total_steps: int
    qa_rejected_steps: int
    qa_rejection_rate: float
    supervisor_iterations: int
    llm_token_total: int
    llm_call_count: int
    llm_latency_p50_ms: int | None
    manual_review_rate: float
    manual_review_is_proxy: bool
    run_wall_clock_seconds: int | None


class ConclusionItemResponse(BaseModel):
    conclusion_id: str
    run_id: str
    step_id: str
    section: str
    claim: str
    confidence: str
    competitor_ids: list[str]
    risk_flags: list[str]
    evidence_ids: list[str]
    created_at: str


class RunConclusionsResponse(BaseModel):
    run_id: str
    items: list[ConclusionItemResponse]


class WatchlistCreateRequest(BaseModel):
    competitor_id: str
    note: str | None = None
    next_refresh_at: datetime | None = None

    @field_validator("competitor_id")
    @classmethod
    def _validate_competitor_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("competitor_id cannot be empty.")
        return normalized

    @field_validator("note")
    @classmethod
    def _normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class WatchlistItemResponse(BaseModel):
    watch_id: str
    competitor_id: str
    note: str | None
    next_refresh_at: str | None
    created_at: str


def _to_sse_chunk(*, event: str, data: dict[str, object]) -> str:
    serialized = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {serialized}\n\n"


def _event_bus_from_request(request: Request) -> EventBus | None:
    event_bus = getattr(request.app.state, "event_bus", None)
    if isinstance(event_bus, EventBus):
        return event_bus
    return None


def _register_background_task(request: Request, task: asyncio.Task[object]) -> None:
    background_tasks = getattr(request.app.state, "background_tasks", None)
    if not isinstance(background_tasks, set):
        return
    background_tasks.add(task)

    def _on_done(finished_task: asyncio.Task[object]) -> None:
        background_tasks.discard(finished_task)
        if finished_task.cancelled():
            return
        task_exc = finished_task.exception()
        if task_exc is not None:
            log.error(
                "api.background_task.failed",
                task_name=finished_task.get_name(),
                exc_type=type(task_exc).__name__,
                error=format_exception_for_log(task_exc),
            )

    task.add_done_callback(_on_done)


def _build_run_finish_payload(
    *,
    run_id: str,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"run_id": run_id, "status": status}
    if error_type is not None:
        payload["error_type"] = error_type
    if error_message is not None:
        payload["error_message"] = error_message[:500]
    return payload


async def _mark_run_failed_and_emit(
    *,
    run_id: str,
    exc: BaseException,
    log_event: str,
) -> None:
    """Background-task boundary cleanup: persist run.status=failed + emit RUN_FINISH.

    Centralises the failure path so all three async graph runners stay in lockstep
    when a node throws an unexpected error. Without this the asyncio task dies
    silently ("Task exception was never retrieved") and the Run row stays
    "running" forever, leaving the UI polling against a corpse.
    """
    error_type = type(exc).__name__
    error_message = format_exception_for_log(exc)
    log.error(log_event, error_type=error_type, error=error_message)
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is not None:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.RUN_FINISH,
        payload=_build_run_finish_payload(
            run_id=run_id,
            status="failed",
            error_type=error_type,
            error_message=error_message,
        ),
    )


_RUN_TASK_NAME_PREFIXES: tuple[str, ...] = (
    "run_graph_",
    "intake_resume_",
    "plan_resume_",
)


async def _handle_graph_cancelled(*, run_id: str, log_event: str) -> None:
    """Reconcile the Run row when a graph task receives CancelledError.

    Two ways this fires:
      1. User cancel via PATCH /runs — the endpoint already flipped the row to
         "cancelled" and emitted RUN_FINISH, so this branch is a no-op.
      2. Unexpected cancellation (e.g. lifespan shutdown asking tasks to stop) —
         the row is still "running"; mark it failed so the UI doesn't hang.
    The caller MUST re-raise CancelledError per asyncio's cooperative-cancel
    contract; failing to do so makes the task look like a normal completion.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        if run.status != "running":
            with bind_run(run_id):
                log.info(log_event, status=run.status, branch="already_terminal")
            return
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
    with bind_run(run_id):
        log.warning(log_event, status="failed", branch="unexpected_cancel")
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.RUN_FINISH,
        payload=_build_run_finish_payload(
            run_id=run_id,
            status="failed",
            error_type="CancelledError",
            error_message="后台任务被中止（可能是服务重启）",
        ),
    )


def _cancel_background_tasks_for_run(
    *,
    background_tasks: set[asyncio.Task[object]] | None,
    run_id: str,
) -> int:
    """Cancel any in-flight graph tasks bound to this run.

    Tasks are named with the run_id suffix on creation (see `name=f"..._{run_id}"`
    in this module). We don't cancel the skill_curator follow-up — it only fires
    on terminal completion, so a cancel during execution means there's no curator
    task to chase yet. CancelledError propagates back through the outer boundary
    (`_mark_run_failed_and_emit`), which would normally flip the row to failed;
    PATCH /runs caller flips it to "cancelled" first so the user's intent wins.
    """
    if not isinstance(background_tasks, set):
        return 0
    cancelled = 0
    for task in list(background_tasks):
        name = task.get_name()
        if not any(name.startswith(prefix) and name.endswith(run_id) for prefix in _RUN_TASK_NAME_PREFIXES):
            continue
        if task.done():
            continue
        task.cancel()
        cancelled += 1
    return cancelled


def _coerce_run_status(state: object) -> str:
    if isinstance(state, dict):
        status_raw = state.get("status", "completed")
    else:
        status_raw = "completed"
    status = str(status_raw)
    if status in {"completed", "degraded"}:
        return status
    return "completed"


def _has_checkpoint_state(values: object) -> bool:
    if not isinstance(values, dict):
        return False
    return bool(values)


def _build_reset_state_values(*, reset_to: ResetToStage) -> dict[str, object]:
    values: dict[str, object] = {
        "pending_tool_args": {},
        "pending_review_target_step_id": None,
        "last_completed_node": None,
        "qa_outcome": None,
        "qa_reject_to": None,
        "qa_rejection_count": 0,
        "qa_reasons": [],
        "status": "running",
        "decisions": [],
    }
    if reset_to == "writer":
        values["next_action"] = "writer"
        values["report_draft_done"] = False
        values["pending_tool_args"] = {
            "template_id": None,
            "sections": [*DEFAULT_FOCUS_DIMENSIONS, "differentiation"],
        }
        return values

    values["next_action"] = "analyst"
    values["analysis_done"] = False
    values["report_draft_done"] = False
    values["pending_tool_args"] = {
        "focus_dimensions": [*DEFAULT_FOCUS_DIMENSIONS, "positioning"],
        "parallel_by_dimension": False,
        "require_cross_competitor": True,
    }
    return values


async def _cleanup_trace_for_reset(
    *,
    run_id: str,
    reset_to: ResetToStage,
) -> None:
    session_factory = get_session_factory()
    agent_names = RESET_STAGE_AGENT_NAMES[reset_to]
    decision_tools = RESET_STAGE_DECISION_TOOLS[reset_to]
    async with session_factory() as session:
        # NOTE: reset_to replay is an explicit exception to append-only trace:
        # we intentionally remove replay-target stages and their downstream data.
        if reset_to == "analyst":
            await session.execute(
                delete(ConclusionRecord).where(ConclusionRecord.run_id == run_id)
            )
        await session.execute(delete(Report).where(Report.run_id == run_id))
        await session.execute(
            delete(Step).where(
                Step.run_id == run_id,
                Step.agent_name.in_(agent_names),
            )
        )
        await session.execute(
            delete(SupervisorDecisionRecord).where(
                SupervisorDecisionRecord.run_id == run_id,
                SupervisorDecisionRecord.chosen_tool.in_(decision_tools),
            )
        )
        await session.commit()


async def _run_event_stream(
    *,
    event_bus: EventBus,
    run_id: str,
    keepalive_seconds: float = 15.0,
    max_events: int | None = None,
) -> AsyncIterator[str]:
    yield "retry: 15000\n\n"
    emitted_count = 0
    async with event_bus.subscribe(run_id) as queue:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            except asyncio.CancelledError:
                return
            yield _to_sse_chunk(
                event=event.event_type.value,
                data=event.model_dump(mode="json"),
            )
            emitted_count += 1
            if max_events is not None and emitted_count >= max_events:
                return


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _derive_run_phase(run: Run) -> Literal["intake", "planning", "executing", "done"] | None:
    """Phase is a derived view, not stored — the source of truth is the LangGraph state.

    Legacy runs (created via POST /api/runs without intake) have `intake_draft is None`
    and return `None` here so the FE renders them with the old layout.

    Phase 2: `plan_tree.confirmed_at` is the planning→executing signal. planner_generate
    writes `confirmed_at=None`; planner_wait sets it on resume.
    """
    intake_draft = run.intake_draft
    if intake_draft is None:
        return None
    if run.status in {"completed", "degraded", "failed"}:
        return "done"
    plan_tree = run.plan_tree
    if plan_tree is not None:
        if plan_tree.get("confirmed_at") is not None:
            return "executing"
        return "planning"
    intake_complete = bool(intake_draft.get("user_role")) and bool(
        intake_draft.get("analysis_intent")
    ) and (
        bool(intake_draft.get("competitors_explicit"))
        or bool(intake_draft.get("competitors_discovery_mode"))
    )
    if not intake_complete:
        return "intake"
    return "planning"


def _to_run_detail(run: Run) -> RunDetailResponse:
    return RunDetailResponse(
        run_id=run.run_id,
        user_query=run.user_query,
        title=run.title,
        domain_hint=run.domain_hint if run.domain_hint else None,
        reference_urls=list(run.reference_urls or []),
        status=run.status,
        target_roles=list(run.target_roles),
        competitors=list(run.competitors),
        started_at=run.started_at.isoformat(),
        finished_at=_to_iso(run.finished_at),
        created_at=run.created_at.isoformat(),
        phase=_derive_run_phase(run),
        intake_draft=dict(run.intake_draft) if run.intake_draft is not None else None,
        plan_tree=dict(run.plan_tree) if run.plan_tree is not None else None,
    )


def _to_step_trace_response(step: Step) -> StepTraceResponse:
    return StepTraceResponse(
        step_id=step.step_id,
        run_id=step.run_id,
        agent_name=step.agent_name,
        status=step.status,
        retry_count=step.retry_count,
        payload=step.payload,
        started_at=step.started_at.isoformat(),
        finished_at=_to_iso(step.finished_at),
        created_at=step.created_at.isoformat(),
    )


def _to_supervisor_decision_trace_response(
    decision: SupervisorDecisionRecord,
) -> SupervisorDecisionTraceResponse:
    return SupervisorDecisionTraceResponse(
        id=decision.id,
        run_id=decision.run_id,
        iteration=decision.iteration,
        chosen_tool=decision.chosen_tool,
        tool_args=decision.tool_args,
        reasoning_summary=decision.reasoning_summary,
        triggered_by=decision.triggered_by,
        outcome=decision.outcome,
        outcome_recorded_at=_to_iso(decision.outcome_recorded_at),
        created_at=decision.created_at.isoformat(),
    )


def _to_llm_call_trace_response(llm_call: LLMCall) -> LLMCallTraceResponse:
    return LLMCallTraceResponse(
        id=llm_call.id,
        step_id=llm_call.step_id,
        model_slot=llm_call.model_slot,
        provider=llm_call.provider,
        model_name=llm_call.model_name,
        prompt_hash=llm_call.prompt_hash,
        prompt_preview=llm_call.prompt_preview,
        prompt_tokens=llm_call.prompt_tokens,
        completion_tokens=llm_call.completion_tokens,
        latency_ms=llm_call.latency_ms,
        error=llm_call.error,
        fallback_used=llm_call.fallback_used,
        fallback_reason=llm_call.fallback_reason,
        created_at=llm_call.created_at.isoformat(),
    )


def _build_trace_timeline(
    *,
    step_rows: list[Step],
    decision_rows: list[SupervisorDecisionRecord],
    llm_rows: list[LLMCall],
) -> list[TraceTimelineItemResponse]:
    timeline_rows: list[tuple[datetime, int, TraceTimelineItemResponse]] = []
    step_agent_by_id = {step.step_id: step.agent_name for step in step_rows}

    for step in step_rows:
        timeline_rows.append(
            (
                step.created_at,
                0,
                TraceTimelineItemResponse(
                    kind="step",
                    timestamp=step.created_at.isoformat(),
                    step_id=step.step_id,
                    agent_name=step.agent_name,
                    summary=f"{step.agent_name} {step.status}",
                    payload={
                        "status": step.status,
                        "retry_count": step.retry_count,
                        "started_at": step.started_at.isoformat(),
                        "finished_at": _to_iso(step.finished_at),
                    },
                ),
            )
        )

    for decision in decision_rows:
        summary_parts = [decision.chosen_tool]
        if decision.outcome:
            summary_parts.append(decision.outcome)
        timeline_rows.append(
            (
                decision.created_at,
                1,
                TraceTimelineItemResponse(
                    kind="decision",
                    timestamp=decision.created_at.isoformat(),
                    step_id=None,
                    agent_name="supervisor",
                    summary=" ".join(summary_parts),
                    payload={
                        "decision_id": decision.id,
                        "iteration": decision.iteration,
                        "chosen_tool": decision.chosen_tool,
                        "triggered_by": decision.triggered_by,
                        "outcome": decision.outcome,
                    },
                ),
            )
        )

    for llm_call in llm_rows:
        provider_label = llm_call.provider or "unknown_provider"
        timeline_rows.append(
            (
                llm_call.created_at,
                2,
                TraceTimelineItemResponse(
                    kind="llm_call",
                    timestamp=llm_call.created_at.isoformat(),
                    step_id=llm_call.step_id,
                    agent_name=step_agent_by_id.get(llm_call.step_id),
                    summary=f"{llm_call.model_slot} {provider_label}",
                    payload={
                        "llm_call_id": llm_call.id,
                        "model_slot": llm_call.model_slot,
                        "provider": llm_call.provider,
                        "model_name": llm_call.model_name,
                        "prompt_hash": llm_call.prompt_hash,
                        "prompt_preview": llm_call.prompt_preview,
                        "prompt_tokens": llm_call.prompt_tokens,
                        "completion_tokens": llm_call.completion_tokens,
                        "latency_ms": llm_call.latency_ms,
                        "error": llm_call.error,
                        "fallback_used": llm_call.fallback_used,
                        "fallback_reason": llm_call.fallback_reason,
                    },
                ),
            )
        )

    timeline_rows.sort(key=lambda row: (row[0], row[1]))
    return [item for _, _, item in timeline_rows]


def _build_run_summary_fields(
    *,
    snapshot: RunMetricsSnapshot,
    status: str,
) -> dict[str, object]:
    return {
        "status": status,
        "run_wall_clock_seconds": snapshot.run_wall_clock_seconds,
        "llm_call_count": snapshot.llm_call_count,
        "llm_token_total": snapshot.llm_token_total,
        "llm_latency_p50_ms": snapshot.llm_latency_p50_ms,
        "coverage_rate": snapshot.coverage_rate,
        "evidence_count_total": snapshot.evidence_count_total,
        "qa_rejection_rate": snapshot.qa_rejection_rate,
        "supervisor_iterations": snapshot.supervisor_iterations,
    }


def _to_watchlist_item(item: WatchlistItem) -> WatchlistItemResponse:
    return WatchlistItemResponse(
        watch_id=item.watch_id,
        competitor_id=item.competitor_id,
        note=item.note,
        next_refresh_at=_to_iso(item.next_refresh_at),
        created_at=item.created_at.isoformat(),
    )


def _extract_competitor_id(span: dict[str, object] | None) -> str | None:
    if not isinstance(span, dict):
        return None
    competitor_id = span.get("competitor_id")
    return competitor_id if isinstance(competitor_id, str) else None


def _normalize_competitor_inputs(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _competitor_seed_file_path() -> Path:
    if settings.DEMO_FIXTURES_DIR:
        return Path(settings.DEMO_FIXTURES_DIR) / "competitors_seed.yaml"
    docker_mount = Path("/demo_fixtures/competitors_seed.yaml")
    if docker_mount.exists():
        return docker_mount
    # backend/app/router/run_rt.py -> backend/demo_fixtures
    return Path(__file__).resolve().parents[2] / "demo_fixtures" / "competitors_seed.yaml"


def _load_competitor_seed_rows() -> list[dict[str, object]]:
    path = _competitor_seed_file_path()
    if not path.exists():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    competitors_raw: object
    if isinstance(loaded, list):
        competitors_raw = loaded
    elif isinstance(loaded, dict):
        competitors_raw = loaded.get("competitors")
    else:
        return []
    if not isinstance(competitors_raw, list):
        return []
    rows: list[dict[str, object]] = []
    for item in competitors_raw:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _validate_competitors(payload: RunCreateRequest) -> list[str]:
    """Normalize competitor inputs. Empty list is allowed (discovery mode)."""
    return _normalize_competitor_inputs(payload.competitors)


@router.get("/api/runs", response_model=RunListResponse)
async def list_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    normalized_status = status.strip() if isinstance(status, str) else None
    session_factory = get_session_factory()
    async with session_factory() as session:
        step_count_subquery = (
            select(func.count())
            .select_from(Step)
            .where(Step.run_id == Run.run_id)
            .scalar_subquery()
        )
        evidence_count_subquery = (
            select(func.count())
            .select_from(EvidenceRecord)
            .where(EvidenceRecord.run_id == Run.run_id)
            .scalar_subquery()
        )
        report_count_subquery = (
            select(func.count())
            .select_from(Report)
            .where(Report.run_id == Run.run_id)
            .scalar_subquery()
        )
        list_query = select(
            Run,
            step_count_subquery.label("step_count"),
            evidence_count_subquery.label("evidence_count"),
            report_count_subquery.label("report_count"),
        )
        total_query = select(func.count()).select_from(Run)
        if normalized_status:
            list_query = list_query.where(Run.status == normalized_status)
            total_query = total_query.where(Run.status == normalized_status)
        list_query = list_query.order_by(Run.started_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(list_query)).all()
        total = int((await session.execute(total_query)).scalar_one())

    items: list[RunListItemResponse] = []
    for run, step_count, evidence_count, report_count in rows:
        items.append(
            RunListItemResponse(
                run_id=run.run_id,
                user_query=run.user_query,
                title=run.title,
                domain_hint=run.domain_hint if run.domain_hint else None,
                status=run.status,
                started_at=run.started_at.isoformat(),
                finished_at=_to_iso(run.finished_at),
                created_at=run.created_at.isoformat(),
                step_count=int(step_count),
                evidence_count=int(evidence_count),
                has_report=int(report_count) > 0,
            )
        )
    return RunListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/demo-fixtures/competitors", response_model=list[CompetitorSeedResponse])
async def list_competitor_seeds() -> list[CompetitorSeedResponse]:
    return [CompetitorSeedResponse.model_validate(item) for item in _load_competitor_seed_rows()]


async def _execute_run_graph(
    *,
    run_id: str,
    graph: Any,
    initial_state: dict[str, object],
    domain_hint: str | None,
    background_tasks: set[asyncio.Task[object]],
) -> None:
    """Run the supervisor graph to completion off the request path (Phase 0b async).

    Mirrors the skill-curator background-task pattern: catch the boundary error
    families, persist terminal status, emit run.finish, and return. Unknown errors
    propagate to asyncio so they remain visible instead of being silently hidden.
    """
    session_factory = get_session_factory()
    config = {"configurable": {"thread_id": run_id}}
    with bind_run(run_id):
        try:
            graph_state = await _run_graph_with_progress_heartbeat(
                run_id=run_id,
                phase="execute",
                graph=graph,
                config=config,
                invoke_coro=graph.ainvoke(initial_state, config=config),
            )
        except asyncio.CancelledError:
            await _handle_graph_cancelled(
                run_id=run_id, log_event="api.run.execute.cancelled"
            )
            raise
        except Exception as exc:
            # Background-task outer boundary: persist failed + RUN_FINISH; do not re-raise
            # or asyncio emits unstructured "Task exception was never retrieved" noise.
            await _mark_run_failed_and_emit(
                run_id=run_id, exc=exc, log_event="api.run.execute.failed"
            )
            return

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"run_id={run_id} should exist after creation")
            run_status = str(graph_state.get("status", "completed"))
            run.status = run_status if run_status in {"completed", "degraded"} else "completed"
            run.finished_at = datetime.now(timezone.utc)
            final_competitors = graph_state.get("competitors")
            if isinstance(final_competitors, list) and final_competitors:
                run.competitors = final_competitors
            await session.commit()
            final_status = run.status
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=final_status),
        )
        await _log_run_summary(run_id=run_id, status=final_status)
        curator_task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=domain_hint),
            name=f"skill_curator_{run_id}",
        )
        background_tasks.add(curator_task)
        curator_task.add_done_callback(background_tasks.discard)
        log.info("api.run.execute.finish", status=final_status)


async def _log_run_summary(*, run_id: str, status: str) -> None:
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                log.warning(
                    "api.run.summary.failed",
                    reason="run_not_found",
                )
                return

            evidence_rows = (
                await session.execute(
                    select(EvidenceRecord)
                    .where(EvidenceRecord.run_id == run_id)
                    .order_by(EvidenceRecord.created_at.asc())
                )
            ).scalars().all()
            step_rows = (
                await session.execute(
                    select(Step)
                    .where(Step.run_id == run_id)
                    .order_by(Step.created_at.asc())
                )
            ).scalars().all()
            llm_rows = (
                await session.execute(
                    select(LLMCall)
                    .join(Step, LLMCall.step_id == Step.step_id)
                    .where(Step.run_id == run_id)
                    .order_by(LLMCall.created_at.asc())
                )
            ).scalars().all()
            decision_rows = (
                await session.execute(
                    select(SupervisorDecisionRecord)
                    .where(SupervisorDecisionRecord.run_id == run_id)
                    .order_by(SupervisorDecisionRecord.created_at.asc())
                )
            ).scalars().all()
            candidate_rows = (
                await session.execute(select(SkillCandidateRecord))
            ).scalars().all()
            candidate_rows = [
                row
                for row in candidate_rows
                if run_id
                in (row.supporting_run_ids if isinstance(row.supporting_run_ids, list) else [])
            ]

        snapshot = build_run_metrics_snapshot(
            run=run,
            evidence_rows=list(evidence_rows),
            step_rows=list(step_rows),
            llm_rows=list(llm_rows),
            decision_rows=list(decision_rows),
            candidate_rows=list(candidate_rows),
        )
        log.info(
            "api.run.summary",
            **_build_run_summary_fields(snapshot=snapshot, status=status),
        )
    except (SQLAlchemyError, TypeError, ValueError, AttributeError) as exc:
        log.warning(
            "api.run.summary.failed",
            error=format_exception_for_log(exc),
        )


@router.post("/api/runs", response_model=RunCreateResponse)
async def create_run(payload: RunCreateRequest, request: Request) -> RunCreateResponse:
    normalized_competitors = _validate_competitors(payload)
    normalized_reference_urls = list(payload.reference_urls or [])
    run_id = make_id("run_")
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info(
            "api.run.create.start",
            domain_hint=payload.domain_hint,
            reference_url_count=len(normalized_reference_urls),
            competitor_count=len(normalized_competitors),
            target_role_count=len(payload.target_roles),
        )

        graph = getattr(request.app.state, "compiled_graph", None)
        if graph is None:
            raise APIException(
                status_code=500,
                error_code="GRAPH_NOT_INITIALIZED",
                message="Compiled LangGraph instance is not initialized.",
            )
        background_tasks = getattr(request.app.state, "background_tasks", None)
        if not isinstance(background_tasks, set):
            raise APIException(
                status_code=500,
                error_code="BACKGROUND_TASKS_NOT_INITIALIZED",
                message="Background task registry is not initialized.",
            )

        async with session_factory() as session:
            session.add(
                Run(
                    run_id=run_id,
                    user_query=payload.user_query,
                    domain_hint=payload.domain_hint,
                    reference_urls=normalized_reference_urls,
                    status="running",
                    target_roles=payload.target_roles,
                    competitors=normalized_competitors,
                )
            )
            await session.commit()

        initial_state: dict[str, object] = {
            "run_id": run_id,
            "domain_hint": payload.domain_hint,
            "reference_urls": normalized_reference_urls,
            "competitors": normalized_competitors,
            "discovered_competitors": [],
            "user_query": payload.user_query,
            "researched_competitors": [],
            "analysis_done": False,
            "report_draft_done": False,
            "current_iteration": 0,
            "pending_tool_args": {},
            "qa_outcome": None,
            "qa_reject_to": None,
            "qa_rejection_count": 0,
            "pending_review_target_step_id": None,
            "qa_reasons": [],
            "status": "running",
        }
        task = asyncio.create_task(
            _execute_run_graph(
                run_id=run_id,
                graph=graph,
                initial_state=initial_state,
                domain_hint=payload.domain_hint,
                background_tasks=background_tasks,
            ),
            name=f"run_graph_{run_id}",
        )
        _register_background_task(request, task)
        log.info("api.run.create.accepted")

    return RunCreateResponse(
        run_id=run_id,
        status="running",
        message="Run accepted; supervisor loop executing in background.",
    )


# --- Phase 1b Agent-native intake (chat mode). Expert mode and plan/confirm
# are intentionally NOT implemented yet — see Phase 2 in the plan doc. ---


def _extract_first_interrupt_value(snapshot: Any) -> Any:
    """Canonical interrupt-payload extraction for langgraph 0.2.50 (Invariant D)."""
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def _coerce_intake_draft_from_state(state_values: dict[str, object]) -> RunIntakeDraft | None:
    raw = state_values.get("intake_draft")
    if isinstance(raw, RunIntakeDraft):
        return raw
    if isinstance(raw, dict):
        return RunIntakeDraft.model_validate(raw)
    return None


def _normalize_idempotency_key(
    *,
    header_value: str | None,
    body_value: str | None,
) -> str:
    """Resolve create-request idempotency key with strict precedence.

    Header key is preferred so upstream gateways / SDK retries can inject it
    without mutating JSON payloads. Falls back to body field for clients that
    cannot set custom headers.
    """
    header_key = header_value.strip() if isinstance(header_value, str) else ""
    if header_key:
        return header_key
    body_key = body_value.strip() if isinstance(body_value, str) else ""
    if body_key:
        return body_key
    return f"idemp_{uuid4().hex}"


def _intake_request_fingerprint(payload: IntakeCreateRequest) -> str:
    """Stable hash for idempotency conflict detection (same key, different body)."""
    canonical: dict[str, object] = {
        "user_query": payload.user_query.strip(),
        "user_role": payload.user_role,
        "domain_hint": payload.domain_hint,
        "reference_urls": list(payload.reference_urls or []),
        "competitors_explicit": list(payload.competitors_explicit),
        "competitors_discovery_mode": payload.competitors_discovery_mode,
        "focus_dimensions": list(payload.focus_dimensions),
        "report_depth": payload.report_depth,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def _persist_intake_draft_to_run(
    *,
    run_id: str,
    state_values: dict[str, object],
) -> None:
    """Snapshot the latest intake_draft from graph state into the Run row.

    Allows GET /api/runs/{id} to render the current intake state without
    re-reading the LangGraph checkpoint.
    """
    draft = _coerce_intake_draft_from_state(state_values)
    if draft is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.intake_draft = draft.model_dump(exclude={"is_complete"})
        await session.commit()


async def _start_intake_graph_in_background(
    *,
    run_id: str,
    graph: Any,
    initial_state: dict[str, object],
    domain_hint: str | None,
    idempotency_key: str,
    background_tasks: set[asyncio.Task[object]],
    accepted_at: datetime,
) -> None:
    """Start intake graph from scratch in background for async create contract."""
    session_factory = get_session_factory()
    config = {"configurable": {"thread_id": run_id}}
    with bind_run(run_id):
        try:
            await _run_graph_with_progress_heartbeat(
                run_id=run_id,
                phase="intake_create",
                graph=graph,
                config=config,
                invoke_coro=graph.ainvoke(initial_state, config=config),
            )
            snapshot = await graph.aget_state(config)
        except asyncio.CancelledError:
            await _handle_graph_cancelled(
                run_id=run_id,
                log_event="api.run.intake.create.cancelled",
            )
            raise
        except Exception as exc:
            async with session_factory() as session:
                record = await session.get(RunCreateRequestRecord, idempotency_key)
                if record is not None:
                    record.status = "failed"
                    record.error_code = type(exc).__name__
                    record.error_message = format_exception_for_log(exc)
                    await session.commit()
            await _mark_run_failed_and_emit(
                run_id=run_id,
                exc=exc,
                log_event="api.run.intake.create.background.failed",
            )
            return

        state_values = snapshot.values if isinstance(snapshot.values, dict) else {}
        await _persist_intake_draft_to_run(run_id=run_id, state_values=state_values)

        async with session_factory() as session:
            record = await session.get(RunCreateRequestRecord, idempotency_key)
            if record is not None:
                record.status = "paused" if snapshot.next else "completed"
                await session.commit()
        if snapshot.next != ():
            next_node = snapshot.next[0] if snapshot.next else None
            log.info(
                "api.run.intake.create.paused",
                next_node=next_node,
                idempotency_key=idempotency_key,
                time_to_first_pause_ms=int(
                    (datetime.now(timezone.utc) - accepted_at).total_seconds() * 1000
                ),
            )
            return

        # Defensive: intake graph might reach terminal unexpectedly; mirror the
        # finalization behavior used by resume paths so run status can't stay running.
        run_status_raw = str(state_values.get("status", "completed"))
        run_status = run_status_raw if run_status_raw in {"completed", "degraded"} else "completed"
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = run_status
                run.finished_at = datetime.now(timezone.utc)
                final_competitors = state_values.get("competitors")
                if isinstance(final_competitors, list) and final_competitors:
                    run.competitors = final_competitors
                await session.commit()
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=run_status),
        )
        curator_task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=domain_hint),
            name=f"skill_curator_{run_id}",
        )
        background_tasks.add(curator_task)
        curator_task.add_done_callback(background_tasks.discard)


async def _resume_plan_graph_in_background(
    *,
    run_id: str,
    graph: Any,
    resume_payload: dict[str, object],
    domain_hint: str | None,
    background_tasks: set[asyncio.Task[object]],
) -> None:
    """Resume the planner-paused graph after the user confirms the plan.

    After planner_wait returns, the graph proceeds to the supervisor and the
    rest of the executor. Terminal handling mirrors `_execute_run_graph`
    (status update, RUN_FINISH event, skill curator follow-up).
    """
    session_factory = get_session_factory()
    config = {"configurable": {"thread_id": run_id}}
    with bind_run(run_id):
        try:
            graph_state = await _run_graph_with_progress_heartbeat(
                run_id=run_id,
                phase="plan_resume",
                graph=graph,
                config=config,
                invoke_coro=graph.ainvoke(Command(resume=resume_payload), config=config),
            )
        except asyncio.CancelledError:
            await _handle_graph_cancelled(
                run_id=run_id, log_event="api.run.plan.resume.cancelled"
            )
            raise
        except Exception as exc:
            await _mark_run_failed_and_emit(
                run_id=run_id, exc=exc, log_event="api.run.plan.resume.failed"
            )
            return

        run_status_raw = str(graph_state.get("status", "completed")) if isinstance(graph_state, dict) else "completed"
        run_status = run_status_raw if run_status_raw in {"completed", "degraded"} else "completed"
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"run_id={run_id} should exist after plan confirm")
            run.status = run_status
            run.finished_at = datetime.now(timezone.utc)
            if isinstance(graph_state, dict):
                final_competitors = graph_state.get("competitors")
                if isinstance(final_competitors, list) and final_competitors:
                    run.competitors = final_competitors
            await session.commit()
            final_status = run.status
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=final_status),
        )
        curator_task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=domain_hint),
            name=f"skill_curator_{run_id}",
        )
        background_tasks.add(curator_task)
        curator_task.add_done_callback(background_tasks.discard)
        log.info("api.run.plan.resume.finish", status=final_status)


async def _resume_intake_graph_in_background(
    *,
    run_id: str,
    graph: Any,
    resume_payload: dict[str, object],
    domain_hint: str | None,
    background_tasks: set[asyncio.Task[object]],
) -> None:
    """Resume the intake-paused graph; either pause again or run to END.

    Either outcome is normal:
      - paused again (more clarification needed): intake_generate already emitted
        INTAKE_CLARIFY_REQUEST inside the graph, so this background path only
        updates the Run row's intake_draft snapshot.
      - reached END: same finalization as `_execute_run_graph` (status, RUN_FINISH,
        skill curator follow-up).
    """
    session_factory = get_session_factory()
    config = {"configurable": {"thread_id": run_id}}
    with bind_run(run_id):
        try:
            await _run_graph_with_progress_heartbeat(
                run_id=run_id,
                phase="intake_resume",
                graph=graph,
                config=config,
                invoke_coro=graph.ainvoke(Command(resume=resume_payload), config=config),
            )
            snapshot = await graph.aget_state(config)
        except asyncio.CancelledError:
            await _handle_graph_cancelled(
                run_id=run_id, log_event="api.run.intake.resume.cancelled"
            )
            raise
        except Exception as exc:
            await _mark_run_failed_and_emit(
                run_id=run_id, exc=exc, log_event="api.run.intake.resume.failed"
            )
            return

        state_values = snapshot.values if isinstance(snapshot.values, dict) else {}
        await _persist_intake_draft_to_run(run_id=run_id, state_values=state_values)

        if snapshot.next != ():
            log.info(
                "api.run.intake.resume.paused",
                next_node=snapshot.next[0] if snapshot.next else None,
            )
            return

        run_status_raw = str(state_values.get("status", "completed"))
        run_status = run_status_raw if run_status_raw in {"completed", "degraded"} else "completed"
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"run_id={run_id} should exist after resume")
            run.status = run_status
            run.finished_at = datetime.now(timezone.utc)
            final_competitors = state_values.get("competitors")
            if isinstance(final_competitors, list) and final_competitors:
                run.competitors = final_competitors
            await session.commit()
            final_status = run.status
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=final_status),
        )
        curator_task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=domain_hint),
            name=f"skill_curator_{run_id}",
        )
        background_tasks.add(curator_task)
        curator_task.add_done_callback(background_tasks.discard)
        log.info("api.run.intake.resume.finish", status=final_status)


@router.post("/api/runs/intake", response_model=IntakeCreateResponse)
async def create_run_intake(
    payload: IntakeCreateRequest,
    request: Request,
    mode: Literal["chat", "expert"] = Query(default="chat"),
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IntakeCreateResponse:
    """Async intake creation: accept quickly, run graph in background.

    Maturity goals:
    - request path must not block on LLM latency;
    - retries / double-clicks should replay idempotently;
    - graph failures are surfaced via events + terminal run status.
    """
    if mode == "expert":
        raise APIException(
            status_code=422,
            error_code="EXPERT_MODE_NOT_AVAILABLE",
            message="Expert mode requires the planner node; available from Phase 2.",
        )

    graph = getattr(request.app.state, "compiled_graph", None)
    if graph is None:
        raise APIException(
            status_code=500,
            error_code="GRAPH_NOT_INITIALIZED",
            message="Compiled LangGraph instance is not initialized.",
        )
    background_tasks = getattr(request.app.state, "background_tasks", None)
    if not isinstance(background_tasks, set):
        raise APIException(
            status_code=500,
            error_code="BACKGROUND_TASKS_NOT_INITIALIZED",
            message="Background task registry is not initialized.",
        )

    idempotency_key = _normalize_idempotency_key(
        header_value=idempotency_key_header,
        body_value=payload.client_request_id,
    )
    request_hash = _intake_request_fingerprint(payload)
    normalized_reference_urls = list(payload.reference_urls or [])
    initial_draft = RunIntakeDraft(
        user_query=payload.user_query,
        user_role=payload.user_role,
        domain_hint=payload.domain_hint,
        competitors_explicit=list(payload.competitors_explicit),
        competitors_discovery_mode=payload.competitors_discovery_mode,
        focus_dimensions=list(payload.focus_dimensions),
        report_depth=payload.report_depth,
        reference_urls=normalized_reference_urls,
    )

    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.get(RunCreateRequestRecord, idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise APIException(
                    status_code=409,
                    error_code="INTAKE_CREATE_IDEMPOTENCY_CONFLICT",
                    message=(
                        "Idempotency-Key 已绑定到不同请求体。"
                        "请更换 key 或重试原请求。"
                    ),
                )
            run = await session.get(Run, existing.run_id)
            if run is None:
                raise APIException(
                    status_code=409,
                    error_code="INTAKE_CREATE_REPLAY_MISSING_RUN",
                    message="幂等记录存在，但关联 run 不存在，请更换 key 重试。",
                )
            replay_draft = (
                RunIntakeDraft.model_validate(run.intake_draft)
                if isinstance(run.intake_draft, dict)
                else initial_draft
            )
            log.info(
                "api.run.intake.create.replay",
                run_id=run.run_id,
                idempotency_key=idempotency_key,
                replay_status=existing.status,
            )
            return IntakeCreateResponse(
                run_id=run.run_id,
                status=run.status,
                phase=_derive_run_phase(run) or "intake",
                intake_draft=replay_draft,
                first_clarify_request=None,
            )

    run_id = make_id("run_")
    accepted_at = datetime.now(timezone.utc)
    with bind_run(run_id):
        log.info(
            "api.run.intake.create.start",
            idempotency_key=idempotency_key,
            user_role=payload.user_role,
            competitor_explicit_count=len(payload.competitors_explicit),
            competitor_discovery_mode=payload.competitors_discovery_mode,
        )

        async with session_factory() as session:
            session.add(
                Run(
                    run_id=run_id,
                    user_query=payload.user_query,
                    domain_hint=payload.domain_hint,
                    reference_urls=normalized_reference_urls,
                    status="running",
                    target_roles=[],
                    competitors=list(payload.competitors_explicit),
                    intake_draft=initial_draft.model_dump(exclude={"is_complete"}),
                )
            )
            session.add(
                RunCreateRequestRecord(
                    idempotency_key=idempotency_key,
                    run_id=run_id,
                    request_hash=request_hash,
                    status="accepted",
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # Concurrent request with same idempotency key won the race.
                await session.rollback()
                existing = await session.get(RunCreateRequestRecord, idempotency_key)
                if existing is None:
                    raise
                if existing.request_hash != request_hash:
                    raise APIException(
                        status_code=409,
                        error_code="INTAKE_CREATE_IDEMPOTENCY_CONFLICT",
                        message=(
                            "Idempotency-Key 已绑定到不同请求体。"
                            "请更换 key 或重试原请求。"
                        ),
                    )
                existing_run = await session.get(Run, existing.run_id)
                if existing_run is None:
                    raise APIException(
                        status_code=409,
                        error_code="INTAKE_CREATE_REPLAY_MISSING_RUN",
                        message="幂等记录存在，但关联 run 不存在，请更换 key 重试。",
                    )
                replay_draft = (
                    RunIntakeDraft.model_validate(existing_run.intake_draft)
                    if isinstance(existing_run.intake_draft, dict)
                    else initial_draft
                )
                return IntakeCreateResponse(
                    run_id=existing_run.run_id,
                    status=existing_run.status,
                    phase=_derive_run_phase(existing_run) or "intake",
                    intake_draft=replay_draft,
                    first_clarify_request=None,
                )

        initial_state: dict[str, object] = {
            "run_id": run_id,
            "user_query": payload.user_query,
            "domain_hint": payload.domain_hint,
            "reference_urls": normalized_reference_urls,
            "competitors": list(payload.competitors_explicit),
            "discovered_competitors": [],
            "researched_competitors": [],
            "analysis_done": False,
            "report_draft_done": False,
            "current_iteration": 0,
            "pending_tool_args": {},
            "qa_outcome": None,
            "qa_reject_to": None,
            "qa_rejection_count": 0,
            "pending_review_target_step_id": None,
            "qa_reasons": [],
            "status": "running",
            "phase": "intake",
            "intake_draft": initial_draft,
            "intake_history": [],
            "pending_clarify": None,
        }
        task = asyncio.create_task(
            _start_intake_graph_in_background(
                run_id=run_id,
                graph=graph,
                initial_state=initial_state,
                domain_hint=payload.domain_hint,
                idempotency_key=idempotency_key,
                background_tasks=background_tasks,
                accepted_at=accepted_at,
            ),
            name=f"intake_create_{run_id}",
        )
        _register_background_task(request, task)

        log.info(
            "api.run.intake.create.accepted",
            phase="intake",
            idempotency_key=idempotency_key,
            intake_create_accept_latency_ms=int(
                (datetime.now(timezone.utc) - accepted_at).total_seconds() * 1000
            ),
        )

    return IntakeCreateResponse(
        run_id=run_id,
        status="running",
        phase="intake",
        intake_draft=initial_draft,
        first_clarify_request=None,
    )


@router.post("/api/runs/{run_id}/intake/reply", response_model=RunAcceptedResponse)
async def reply_run_intake(
    run_id: str,
    payload: IntakeUserReply,
    request: Request,
) -> RunAcceptedResponse:
    """Invariant C: return accepted immediately; resume the graph off the request path.

    The graph re-enters intake_generate after the wait node returns. Whether it
    asks another clarify or completes is observed by the FE via SSE; the response
    body intentionally carries no clarify payload to keep this endpoint cheap.
    """
    graph = getattr(request.app.state, "compiled_graph", None)
    if graph is None:
        raise APIException(
            status_code=500,
            error_code="GRAPH_NOT_INITIALIZED",
            message="Compiled LangGraph instance is not initialized.",
        )
    background_tasks = getattr(request.app.state, "background_tasks", None)
    if not isinstance(background_tasks, set):
        raise APIException(
            status_code=500,
            error_code="BACKGROUND_TASKS_NOT_INITIALIZED",
            message="Background task registry is not initialized.",
        )

    session_factory = get_session_factory()
    with bind_run(run_id):
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )
            if run.status != "running":
                raise APIException(
                    status_code=409,
                    error_code="RUN_NOT_RESUMABLE",
                    message=f"run status={run.status} is not resumable",
                )
            domain_hint = run.domain_hint

        # Verify the graph is actually paused at intake_wait before resuming. Resuming
        # from a non-intake pause would corrupt state by injecting an IntakeUserReply
        # into the wrong node's interrupt payload.
        snapshot = await graph.aget_state({"configurable": {"thread_id": run_id}})
        if snapshot.next != ("intake_wait",):
            raise APIException(
                status_code=409,
                error_code="INTAKE_NOT_AWAITING_REPLY",
                message=(
                    "run is not paused at the intake clarify step; "
                    f"current next_node={list(snapshot.next)}"
                ),
            )

        resume_payload = payload.model_dump()
        task = asyncio.create_task(
            _resume_intake_graph_in_background(
                run_id=run_id,
                graph=graph,
                resume_payload=resume_payload,
                domain_hint=domain_hint,
                background_tasks=background_tasks,
            ),
            name=f"intake_resume_{run_id}",
        )
        _register_background_task(request, task)
        log.info(
            "api.run.intake.reply.accepted",
            reply_text_len=len(payload.text),
            reply_option_count=len(payload.selected_options),
        )

    return RunAcceptedResponse(run_id=run_id, status="running")


@router.post("/api/runs/{run_id}/plan/confirm", response_model=RunAcceptedResponse)
async def confirm_run_plan(
    run_id: str,
    payload: PlanConfirmRequest,
    request: Request,
) -> RunAcceptedResponse:
    """Phase 2 (Invariant C): resume the graph past planner_wait.

    The graph proceeds to the supervisor and the rest of the executor in a
    background task. Phase β honors `disabled_task_ids` (must reference tasks
    in the pending plan) and `additional_tasks` (server forces
    source="user", priority="user_pinned"; the planner_wait node validates
    them and merges into plan_tree).
    """
    graph = getattr(request.app.state, "compiled_graph", None)
    if graph is None:
        raise APIException(
            status_code=500,
            error_code="GRAPH_NOT_INITIALIZED",
            message="Compiled LangGraph instance is not initialized.",
        )
    background_tasks = getattr(request.app.state, "background_tasks", None)
    if not isinstance(background_tasks, set):
        raise APIException(
            status_code=500,
            error_code="BACKGROUND_TASKS_NOT_INITIALIZED",
            message="Background task registry is not initialized.",
        )

    session_factory = get_session_factory()
    with bind_run(run_id):
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )
            if run.status != "running":
                raise APIException(
                    status_code=409,
                    error_code="RUN_NOT_RESUMABLE",
                    message=f"run status={run.status} is not resumable",
                )
            domain_hint = run.domain_hint

        # Verify the graph is actually paused at planner_wait. Resuming from a
        # non-plan pause would inject the PlanConfirmRequest into the wrong
        # interrupt payload (mirrors the intake/reply guard above).
        snapshot = await graph.aget_state({"configurable": {"thread_id": run_id}})
        if snapshot.next != ("planner_wait",):
            raise APIException(
                status_code=409,
                error_code="PLAN_NOT_AWAITING_CONFIRM",
                message=(
                    "run is not paused at the plan-confirm step; "
                    f"current next_node={list(snapshot.next)}"
                ),
            )

        resume_payload = payload.model_dump()
        task = asyncio.create_task(
            _resume_plan_graph_in_background(
                run_id=run_id,
                graph=graph,
                resume_payload=resume_payload,
                domain_hint=domain_hint,
                background_tasks=background_tasks,
            ),
            name=f"plan_resume_{run_id}",
        )
        _register_background_task(request, task)
        log.info(
            "api.run.plan.confirm.accepted",
            disabled_task_count=len(payload.disabled_task_ids),
            additional_task_count=len(payload.additional_tasks),
        )

    return RunAcceptedResponse(run_id=run_id, status="running")


@router.post(
    "/api/runs/{run_id}/follow-up",
    response_model=FollowUpAcceptedResponse,
)
async def submit_run_follow_up(
    run_id: str,
    payload: FollowUpRequest,
    request: Request,
) -> FollowUpAcceptedResponse:
    """Phase 4: append a mid-run user addendum to the supervisor's inbox.

    Persisted on `runs.follow_ups` (JSONB list); the supervisor reads pending
    entries at the start of each iteration, injects them into its prompt,
    then marks them consumed after the LLM decision. We deliberately do NOT
    touch the LangGraph state directly: the graph is mid-execution (not at
    an interrupt), so `aupdate_state` on a running thread is unsafe — the
    DB inbox is the lock-free channel.
    """
    graph = getattr(request.app.state, "compiled_graph", None)
    if graph is None:
        raise APIException(
            status_code=500,
            error_code="GRAPH_NOT_INITIALIZED",
            message="Compiled LangGraph instance is not initialized.",
        )

    session_factory = get_session_factory()
    with bind_run(run_id):
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )
            if run.status != "running":
                raise APIException(
                    status_code=409,
                    error_code="FOLLOWUP_RUN_NOT_RUNNING",
                    message=(
                        f"run status={run.status} cannot accept follow-up "
                        "(must be running and past plan confirmation)"
                    ),
                )
            plan_tree_value = run.plan_tree
            plan_confirmed = (
                isinstance(plan_tree_value, dict)
                and plan_tree_value.get("confirmed_at") is not None
            )
            if not plan_confirmed:
                raise APIException(
                    status_code=409,
                    error_code="FOLLOWUP_NOT_EXECUTING",
                    message=(
                        "follow-up is only accepted after plan confirmation — "
                        "use POST /intake/reply or /plan/confirm instead"
                    ),
                )

        snapshot = await graph.aget_state({"configurable": {"thread_id": run_id}})
        if snapshot.next in {("intake_wait",), ("planner_wait",)}:
            raise APIException(
                status_code=409,
                error_code="FOLLOWUP_GRAPH_PAUSED",
                message=(
                    "graph is paused awaiting a structured reply; "
                    f"use the matching endpoint instead (next_node={list(snapshot.next)})"
                ),
            )

        received_at = datetime.now(timezone.utc).isoformat()
        entry = FollowUpEntry(
            text=payload.text,
            applies_to_stage=payload.applies_to_stage,
            received_at=received_at,
        )
        entry_dict = entry.model_dump(mode="json")

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                # Defensive: another tab could have hit /reset between our two
                # reads. Surface 404 rather than persisting an orphan entry.
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} no longer exists",
                )
            existing = list(run.follow_ups or [])
            existing.append(entry_dict)
            run.follow_ups = existing
            await session.commit()

        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.FOLLOWUP_RECEIVED,
            payload={
                "follow_up_id": entry.id,
                "text": entry.text,
                "applies_to_stage": entry.applies_to_stage,
                "received_at": received_at,
            },
        )
        log.info(
            "api.run.follow_up.accepted",
            follow_up_id=entry.id,
            applies_to_stage=entry.applies_to_stage,
            text_len=len(entry.text),
        )

    return FollowUpAcceptedResponse(
        run_id=run_id,
        follow_up_id=entry.id,
        received_at=received_at,
    )


@router.post("/api/runs/{run_id}/resume", response_model=RunCreateResponse)
async def resume_run(run_id: str, request: Request) -> RunCreateResponse:
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info("api.run.resume.start")
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )
            if run.status != "running":
                raise APIException(
                    status_code=409,
                    error_code="RUN_NOT_RESUMABLE",
                    message=f"run_id={run_id} status={run.status} cannot resume",
                )

        graph = getattr(request.app.state, "compiled_graph", None)
        if graph is None:
            raise APIException(
                status_code=500,
                error_code="GRAPH_NOT_INITIALIZED",
                message="Compiled LangGraph instance is not initialized.",
            )
        graph_state = await graph.ainvoke(None, config={"configurable": {"thread_id": run_id}})

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=500,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} should exist before resume update",
                )
            run_domain_hint = run.domain_hint
            run_status = str(graph_state.get("status", "completed"))
            run.status = run_status if run_status in {"completed", "degraded"} else "completed"
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=run.status),
        )
        task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=run_domain_hint),
            name=f"skill_curator_{run_id}",
        )
        _register_background_task(request, task)
        log.info("api.run.resume.finish", status=run.status)

    return RunCreateResponse(
        run_id=run_id,
        status=run.status,
        message="Run resumed from checkpoint.",
    )


@router.post("/api/runs/{run_id}/reset", response_model=RunCreateResponse)
async def reset_run(run_id: str, payload: RunResetRequest, request: Request) -> RunCreateResponse:
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info("api.run.reset.start", reset_to=payload.reset_to)
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )
            if run.status not in RESETTABLE_RUN_STATUS:
                raise APIException(
                    status_code=409,
                    error_code="RUN_NOT_RESETTABLE",
                    message=f"run_id={run_id} status={run.status} cannot reset",
                )
            run_domain_hint = run.domain_hint

        graph = getattr(request.app.state, "compiled_graph", None)
        if graph is None:
            raise APIException(
                status_code=500,
                error_code="GRAPH_NOT_INITIALIZED",
                message="Compiled LangGraph instance is not initialized.",
            )
        config = {"configurable": {"thread_id": run_id}}
        state_snapshot = await graph.aget_state(config)
        if not _has_checkpoint_state(state_snapshot.values):
            raise APIException(
                status_code=409,
                error_code="RUN_CHECKPOINT_NOT_FOUND",
                message=f"run_id={run_id} has no checkpoint state to reset from",
            )

        await _cleanup_trace_for_reset(run_id=run_id, reset_to=payload.reset_to)

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=500,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} should exist before reset replay",
                )
            run.status = "running"
            run.finished_at = None
            await session.commit()

        reset_values = _build_reset_state_values(reset_to=payload.reset_to)
        await graph.aupdate_state(config, reset_values, as_node="supervisor")
        graph_state = await graph.ainvoke(None, config=config)

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=500,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} should exist before reset status update",
                )
            run.status = _coerce_run_status(graph_state)
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()

        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=run.status),
        )
        task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=run_domain_hint),
            name=f"skill_curator_{run_id}",
        )
        _register_background_task(request, task)
        log.info("api.run.reset.finish", reset_to=payload.reset_to, status=run.status)

    return RunCreateResponse(
        run_id=run_id,
        status=run.status,
        message=f"Run reset to {payload.reset_to} and replayed from checkpoint.",
    )


@router.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str, request: Request) -> StreamingResponse:
    event_bus = _event_bus_from_request(request)
    if event_bus is None:
        raise APIException(
            status_code=503,
            error_code="EVENT_BUS_NOT_INITIALIZED",
            message="Run event stream is not initialized.",
        )

    return StreamingResponse(
        _run_event_stream(event_bus=event_bus, run_id=run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str) -> RunDetailResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        return _to_run_detail(run)


class RunPatchRequest(BaseModel):
    user_query: str | None = None
    # Manual rename for the short title. Use this instead of mutating user_query
    # when the user just wants a cleaner card label — user_query is the
    # original prompt and should stay immutable in most cases.
    title: str | None = Field(default=None, max_length=120)
    status: Literal["cancelled"] | None = None
    cancel_reason: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @field_validator("cancel_reason")
    @classmethod
    def _normalize_cancel_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class RunDeleteResponse(BaseModel):
    run_id: str
    deleted: bool


class BatchDeleteRequest(BaseModel):
    run_ids: list[str] = Field(..., min_length=1, max_length=50)


class BatchDeleteResponse(BaseModel):
    deleted_count: int
    not_found: list[str]


ClearRunsStatus = Literal["all", "completed", "degraded", "failed", "cancelled", "running"]


class ClearRunsRequest(BaseModel):
    status: ClearRunsStatus = "all"
    keyword: str | None = Field(default=None, max_length=200)
    include_running: bool = False

    @field_validator("keyword")
    @classmethod
    def _normalize_keyword(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class ClearRunsResponse(BaseModel):
    deleted_count: int
    deleted_run_ids: list[str]
    skipped_running_count: int
    pruned_skill_candidate_refs: int


async def _prune_supporting_run_refs(
    *,
    session: Any,
    deleted_run_ids: set[str],
) -> int:
    if not deleted_run_ids:
        return 0
    candidates = (await session.execute(select(SkillCandidateRecord))).scalars().all()
    pruned_refs = 0
    for candidate in candidates:
        kept_ids: list[str] = []
        for run_id in candidate.supporting_run_ids:
            if run_id in deleted_run_ids:
                pruned_refs += 1
                continue
            kept_ids.append(run_id)
        if len(kept_ids) != len(candidate.supporting_run_ids):
            candidate.supporting_run_ids = kept_ids
    return pruned_refs


@router.delete("/api/runs/{run_id}", response_model=RunDeleteResponse)
async def delete_run(run_id: str) -> RunDeleteResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        await session.delete(run)
        await session.commit()
    return RunDeleteResponse(run_id=run_id, deleted=True)


@router.patch("/api/runs/{run_id}", response_model=RunDetailResponse)
async def patch_run(
    run_id: str, payload: RunPatchRequest, request: Request
) -> RunDetailResponse:
    """Rename + cooperative cancel.

    Cancel path (status="cancelled" while run is running):
      1. Flip DB to "cancelled" (user intent wins over the background's eventual
         "failed" if its CancelledError races back).
      2. Cancel any in-flight graph tasks named with this run_id.
      3. Emit RUN_FINISH so SSE consumers (LiveRunPage) stop polling immediately.
    """
    should_cancel_tasks = False
    cancel_reason = payload.cancel_reason
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        if payload.user_query is not None:
            run.user_query = payload.user_query
        if payload.title is not None:
            run.title = payload.title
        if payload.status == "cancelled" and run.status == "running":
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
            should_cancel_tasks = True
        await session.commit()
        await session.refresh(run)

    if should_cancel_tasks:
        background_tasks = getattr(request.app.state, "background_tasks", None)
        cancelled_count = _cancel_background_tasks_for_run(
            background_tasks=background_tasks if isinstance(background_tasks, set) else None,
            run_id=run_id,
        )
        with bind_run(run_id):
            log.info(
                "api.run.cancel",
                cancelled_task_count=cancelled_count,
                cancel_reason=cancel_reason,
            )
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(
                run_id=run_id,
                status="cancelled",
                error_type="UserCancelled",
                error_message=cancel_reason or "用户已停止此次分析",
            ),
        )
    return _to_run_detail(run)


@router.post("/api/runs/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_runs(payload: BatchDeleteRequest) -> BatchDeleteResponse:
    session_factory = get_session_factory()
    not_found: list[str] = []
    deleted_count = 0
    async with session_factory() as session:
        for rid in payload.run_ids:
            run = await session.get(Run, rid)
            if run is None:
                not_found.append(rid)
            else:
                await session.delete(run)
                deleted_count += 1
        await session.commit()
    return BatchDeleteResponse(deleted_count=deleted_count, not_found=not_found)


@router.post("/api/runs/clear", response_model=ClearRunsResponse)
async def clear_runs(payload: ClearRunsRequest) -> ClearRunsResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        query = select(Run.run_id, Run.status)
        if payload.status != "all":
            query = query.where(Run.status == payload.status)
        if payload.keyword is not None:
            query = query.where(Run.user_query.ilike(f"%{payload.keyword}%"))
        rows = (await session.execute(query)).all()

        run_ids_to_delete: list[str] = []
        skipped_running_count = 0
        for run_id, status in rows:
            if status == "running" and not payload.include_running:
                skipped_running_count += 1
                continue
            run_ids_to_delete.append(run_id)
        deleted_run_ids_set = set(run_ids_to_delete)
        pruned_skill_candidate_refs = await _prune_supporting_run_refs(
            session=session,
            deleted_run_ids=deleted_run_ids_set,
        )
        if run_ids_to_delete:
            await session.execute(delete(Run).where(Run.run_id.in_(run_ids_to_delete)))
        await session.commit()
    return ClearRunsResponse(
        deleted_count=len(run_ids_to_delete),
        deleted_run_ids=run_ids_to_delete,
        skipped_running_count=skipped_running_count,
        pruned_skill_candidate_refs=pruned_skill_candidate_refs,
    )


@router.get("/api/runs/{run_id}/report", response_model=RunReportResponse)
async def get_run_report(run_id: str) -> RunReportResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        report = (
            await session.execute(
                select(Report).where(Report.run_id == run_id).order_by(Report.created_at.desc()).limit(1)
            )
        ).scalars().first()
        if report is None:
            raise APIException(
                status_code=404,
                error_code="REPORT_NOT_FOUND",
                message=f"report for run_id={run_id} does not exist",
            )
        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()

    evidence_id_to_brief: dict[str, EvidenceBriefResponse] = {}
    for evidence in evidence_rows:
        evidence_id_to_brief[evidence.id] = EvidenceBriefResponse(
            evidence_id=evidence.id,
            source_type=evidence.source_type,
            source_url=evidence.source_url,
            source_title=evidence.source_title,
            competitor_id=_extract_competitor_id(evidence.span),
        )

    return RunReportResponse(
        run_id=run.run_id,
        status=run.status,
        content_markdown=report.content_markdown,
        content_json=report.content_json,
        generated_at=report.created_at.isoformat(),
        evidence_id_to_brief=evidence_id_to_brief,
    )


@router.get("/api/runs/{run_id}/evidence", response_model=list[EvidenceListItemResponse])
async def get_run_evidence(
    run_id: str,
    competitor_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
) -> list[EvidenceListItemResponse]:
    normalized_competitor_id = competitor_id.strip() if isinstance(competitor_id, str) else None
    normalized_source_type = source_type.strip() if isinstance(source_type, str) else None
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        query = select(EvidenceRecord).where(EvidenceRecord.run_id == run_id)
        if normalized_source_type:
            query = query.where(EvidenceRecord.source_type == normalized_source_type)
        evidence_rows = (
            await session.execute(query.order_by(EvidenceRecord.created_at.asc()))
        ).scalars().all()

    if normalized_competitor_id:
        evidence_rows = [
            item
            for item in evidence_rows
            if _extract_competitor_id(item.span) == normalized_competitor_id
        ]

    return [
        EvidenceListItemResponse(
            evidence_id=evidence.id,
            run_id=evidence.run_id,
            source_type=evidence.source_type,
            source_url=evidence.source_url,
            source_title=evidence.source_title,
            sanitized_text=evidence.sanitized_text,
            competitor_id=_extract_competitor_id(evidence.span),
            metadata=evidence.span,
            collected_at=evidence.collected_at.isoformat(),
            created_at=evidence.created_at.isoformat(),
        )
        for evidence in evidence_rows
    ]


@router.get("/api/runs/{run_id}/conclusions", response_model=RunConclusionsResponse)
async def get_run_conclusions(run_id: str) -> RunConclusionsResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )
        items_raw = await load_conclusions_for_run(session=session, run_id=run_id)

    return RunConclusionsResponse(
        run_id=run_id,
        items=[ConclusionItemResponse.model_validate(item) for item in items_raw],
    )


@router.get("/api/watchlist", response_model=list[WatchlistItemResponse])
async def list_watchlist() -> list[WatchlistItemResponse]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(WatchlistItem).order_by(WatchlistItem.created_at.desc(), WatchlistItem.competitor_id.asc())
            )
        ).scalars().all()
    return [_to_watchlist_item(item) for item in rows]


@router.post("/api/watchlist", response_model=WatchlistItemResponse)
async def create_watchlist_item(payload: WatchlistCreateRequest) -> WatchlistItemResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = (
            await session.execute(
                select(WatchlistItem).where(WatchlistItem.competitor_id == payload.competitor_id)
            )
        ).scalars().first()
        if existing is not None:
            raise APIException(
                status_code=409,
                error_code="WATCHLIST_ALREADY_EXISTS",
                message=f"competitor_id={payload.competitor_id} already exists in watchlist",
            )
        item = WatchlistItem(
            watch_id=make_id("watch_"),
            competitor_id=payload.competitor_id,
            note=payload.note,
            next_refresh_at=payload.next_refresh_at,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
    return _to_watchlist_item(item)


@router.delete("/api/watchlist/{watch_id}", response_model=WatchlistItemResponse)
async def delete_watchlist_item(watch_id: str) -> WatchlistItemResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        item = await session.get(WatchlistItem, watch_id)
        if item is None:
            raise APIException(
                status_code=404,
                error_code="WATCHLIST_ITEM_NOT_FOUND",
                message=f"watch_id={watch_id} does not exist",
            )
        deleted_item = _to_watchlist_item(item)
        await session.delete(item)
        await session.commit()
    return deleted_item


@router.get("/api/runs/{run_id}/metrics", response_model=RunMetricsResponse)
async def get_run_metrics(run_id: str) -> RunMetricsResponse:
    """
    Runtime business-loop metrics for scoring and demo checkpoints.

    manual_review_rate is a proxy metric based on reviewed skill candidates
    linked to this run, not direct evaluator edits on report content.
    """

    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise APIException(
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"run_id={run_id} does not exist",
            )

        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()
        step_rows = (
            await session.execute(select(Step).where(Step.run_id == run_id).order_by(Step.created_at.asc()))
        ).scalars().all()
        llm_rows = (
            await session.execute(
                select(LLMCall)
                .join(Step, LLMCall.step_id == Step.step_id)
                .where(Step.run_id == run_id)
                .order_by(LLMCall.created_at.asc())
            )
        ).scalars().all()
        decision_rows = (
            await session.execute(
                select(SupervisorDecisionRecord)
                .where(SupervisorDecisionRecord.run_id == run_id)
                .order_by(SupervisorDecisionRecord.created_at.asc())
            )
        ).scalars().all()
        candidate_rows = (
            await session.execute(select(SkillCandidateRecord))
        ).scalars().all()
        candidate_rows = [
            row
            for row in candidate_rows
            if run_id in (row.supporting_run_ids if isinstance(row.supporting_run_ids, list) else [])
        ]

    snapshot = build_run_metrics_snapshot(
        run=run,
        evidence_rows=evidence_rows,
        step_rows=step_rows,
        llm_rows=llm_rows,
        decision_rows=decision_rows,
        candidate_rows=candidate_rows,
    )
    return RunMetricsResponse(**asdict(snapshot))


@router.get("/api/runs/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(run_id: str) -> RunTraceResponse:
    session_factory = get_session_factory()
    with bind_run(run_id):
        log.info("api.run.trace.query.start")
        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=404,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} does not exist",
                )

            step_rows = (
                await session.execute(
                    select(Step).where(Step.run_id == run_id).order_by(Step.created_at.asc())
                )
            ).scalars().all()
            decision_rows = (
                await session.execute(
                    select(SupervisorDecisionRecord)
                    .where(SupervisorDecisionRecord.run_id == run_id)
                    .order_by(SupervisorDecisionRecord.created_at.asc())
                )
            ).scalars().all()
            llm_rows = (
                await session.execute(
                    select(LLMCall)
                    .join(Step, LLMCall.step_id == Step.step_id)
                    .where(Step.run_id == run_id)
                    .order_by(LLMCall.created_at.asc())
                )
            ).scalars().all()
        log.info(
            "api.run.trace.query.finish",
            step_count=len(step_rows),
            decision_count=len(decision_rows),
            llm_call_count=len(llm_rows),
        )

    return RunTraceResponse(
        run=_to_run_detail(run),
        steps=[_to_step_trace_response(step) for step in step_rows],
        supervisor_decisions=[
            _to_supervisor_decision_trace_response(decision) for decision in decision_rows
        ],
        llm_calls=[_to_llm_call_trace_response(llm_call) for llm_call in llm_rows],
        timeline=_build_trace_timeline(
            step_rows=list(step_rows),
            decision_rows=list(decision_rows),
            llm_rows=list(llm_rows),
        ),
    )
