from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
import yaml

from db.engine import get_session_factory
from core.config import settings
from exceptions.base import APIException
from models.conclusion import ConclusionRecord
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.report import Report
from models.run import Run
from models.skill_candidate import SkillCandidateRecord
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord
from models.watchlist import WatchlistItem
from schemas.ids import make_id
from schemas.intake import IntakeClarifyRequest, IntakeUserReply, RunIntakeDraft, UserRole
from schemas.plan import FollowUpEntry, FollowUpRequest, PlanConfirmRequest
from service.conclusion import load_conclusions_for_run
from service.event_bus import EventBus, RunEventType, emit_run_event
from service.metrics import build_run_metrics_snapshot
from service.skill_curator.tasks import run_skill_curator_for_run
from utils.logger import bind_run, get_logger

router = APIRouter()
log = get_logger("router.run_rt")

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


class IntakeCreateResponse(BaseModel):
    run_id: str
    status: str
    phase: str
    intake_draft: RunIntakeDraft
    # Invariant D: chat mode returns the first clarify question synchronously so the
    # client can render it immediately; expert mode returns None (draft already complete).
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


class RunTraceResponse(BaseModel):
    run: RunDetailResponse
    steps: list[StepTraceResponse]
    supervisor_decisions: list[SupervisorDecisionTraceResponse]


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

    def _discard(finished_task: asyncio.Task[object]) -> None:
        background_tasks.discard(finished_task)

    task.add_done_callback(_discard)


def _build_run_finish_payload(*, run_id: str, status: str) -> dict[str, object]:
    return {"run_id": run_id, "status": status}


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
            "sections": ["feature", "pricing", "user_feedback", "differentiation"],
        }
        return values

    values["next_action"] = "analyst"
    values["analysis_done"] = False
    values["report_draft_done"] = False
    values["pending_tool_args"] = {
        "focus_dimensions": ["feature", "pricing", "user_feedback", "positioning"],
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
    intake_complete = bool(intake_draft.get("user_role")) and bool(
        intake_draft.get("analysis_intent")
    ) and (
        bool(intake_draft.get("competitors_explicit"))
        or bool(intake_draft.get("competitors_discovery_mode"))
    )
    if not intake_complete:
        return "intake"
    plan_tree = run.plan_tree
    if plan_tree is None or plan_tree.get("confirmed_at") is None:
        return "planning"
    return "executing"


def _to_run_detail(run: Run) -> RunDetailResponse:
    return RunDetailResponse(
        run_id=run.run_id,
        user_query=run.user_query,
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
    with bind_run(run_id):
        try:
            graph_state = await graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": run_id}},
            )
        except (APIException, SQLAlchemyError, RuntimeError) as exc:
            log.exception("api.run.execute.failed", error=str(exc)[:500])
            async with session_factory() as session:
                run = await session.get(Run, run_id)
                if run is not None:
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    await session.commit()
            await emit_run_event(
                run_id=run_id,
                event_type=RunEventType.RUN_FINISH,
                payload=_build_run_finish_payload(run_id=run_id, status="failed"),
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
        curator_task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=domain_hint),
            name=f"skill_curator_{run_id}",
        )
        background_tasks.add(curator_task)
        curator_task.add_done_callback(background_tasks.discard)
        log.info("api.run.execute.finish", status=final_status)


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
            graph_state = await graph.ainvoke(Command(resume=resume_payload), config=config)
        except (APIException, SQLAlchemyError, RuntimeError) as exc:
            log.exception("api.run.plan.resume.failed", error=str(exc)[:500])
            async with session_factory() as session:
                run = await session.get(Run, run_id)
                if run is not None:
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    await session.commit()
            await emit_run_event(
                run_id=run_id,
                event_type=RunEventType.RUN_FINISH,
                payload=_build_run_finish_payload(run_id=run_id, status="failed"),
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
            await graph.ainvoke(Command(resume=resume_payload), config=config)
            snapshot = await graph.aget_state(config)
        except (APIException, SQLAlchemyError, RuntimeError) as exc:
            log.exception("api.run.intake.resume.failed", error=str(exc)[:500])
            async with session_factory() as session:
                run = await session.get(Run, run_id)
                if run is not None:
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    await session.commit()
            await emit_run_event(
                run_id=run_id,
                event_type=RunEventType.RUN_FINISH,
                payload=_build_run_finish_payload(run_id=run_id, status="failed"),
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
) -> IntakeCreateResponse:
    """Phase 1b chat-mode intake creation.

    Invariant D: ainvoke synchronously until the first interrupt, read the clarify
    payload from the snapshot, return it inline so the FE renders the first
    question without an SSE round-trip.

    Expert mode is intentionally 422 in Phase 1b — it would need to skip intake
    and enter the planner, which Phase 2 implements. Returning 422 keeps the API
    contract honest instead of silently routing expert traffic through chat.
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

    run_id = make_id("run_")
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
    with bind_run(run_id):
        log.info(
            "api.run.intake.create.start",
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
            await session.commit()

        config = {"configurable": {"thread_id": run_id}}
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
        try:
            await graph.ainvoke(initial_state, config=config)
        except (APIException, SQLAlchemyError, RuntimeError) as exc:
            log.exception("api.run.intake.create.failed", error=str(exc)[:500])
            async with session_factory() as session:
                run = await session.get(Run, run_id)
                if run is not None:
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    await session.commit()
            raise APIException(
                status_code=500,
                error_code="INTAKE_GRAPH_FAILED",
                message=f"intake graph invocation failed: {exc}",
            ) from exc

        snapshot = await graph.aget_state(config)
        state_values = snapshot.values if isinstance(snapshot.values, dict) else {}
        await _persist_intake_draft_to_run(run_id=run_id, state_values=state_values)
        final_draft = _coerce_intake_draft_from_state(state_values) or initial_draft

        first_clarify: IntakeClarifyRequest | None = None
        phase_out: str
        if snapshot.next == ("intake_wait",):
            clarify_raw = _extract_first_interrupt_value(snapshot)
            if clarify_raw is None:
                raise APIException(
                    status_code=500,
                    error_code="INTAKE_CLARIFY_MISSING",
                    message="intake graph paused without an interrupt payload",
                )
            first_clarify = IntakeClarifyRequest.model_validate(clarify_raw)
            phase_out = "intake"
        elif snapshot.next == ():
            # Edge case: the IntakeAgent decided complete on turn 1 and the graph ran
            # the full pipeline inside this request. Status reflects the terminal state.
            run_status_raw = str(state_values.get("status", "completed"))
            run_status = run_status_raw if run_status_raw in {"completed", "degraded"} else "completed"
            async with session_factory() as session:
                run = await session.get(Run, run_id)
                if run is not None:
                    run.status = run_status
                    run.finished_at = datetime.now(timezone.utc)
                    await session.commit()
            phase_out = "done"
        else:
            phase_out = "intake"

        log.info(
            "api.run.intake.create.accepted",
            paused_at=snapshot.next[0] if snapshot.next else None,
            draft_complete=bool(final_draft.is_complete),
        )

    return IntakeCreateResponse(
        run_id=run_id,
        status="running",
        phase=phase_out,
        intake_draft=final_draft,
        first_clarify_request=first_clarify,
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
    background task. Phase α only honors `disabled_task_ids`; the planner_wait
    node silently drops `additional_tasks` until Phase β enables them.
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
    status: Literal["cancelled"] | None = None


class RunDeleteResponse(BaseModel):
    run_id: str
    deleted: bool


class BatchDeleteRequest(BaseModel):
    run_ids: list[str] = Field(..., min_length=1, max_length=50)


class BatchDeleteResponse(BaseModel):
    deleted_count: int
    not_found: list[str]


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
async def patch_run(run_id: str, payload: RunPatchRequest) -> RunDetailResponse:
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
        if payload.status == "cancelled" and run.status == "running":
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(run)
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
        log.info(
            "api.run.trace.query.finish",
            step_count=len(step_rows),
            decision_count=len(decision_rows),
        )

    return RunTraceResponse(
        run=_to_run_detail(run),
        steps=[
            StepTraceResponse(
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
            for step in step_rows
        ],
        supervisor_decisions=[
            SupervisorDecisionTraceResponse(
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
            for decision in decision_rows
        ],
    )
