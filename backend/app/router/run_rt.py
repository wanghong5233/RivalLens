from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
import yaml

from db.engine import get_session_factory
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
    return Path(__file__).resolve().parents[3] / "demo_fixtures" / "competitors_seed.yaml"


def _load_competitor_seed_rows() -> list[dict[str, object]]:
    path = _competitor_seed_file_path()
    if not path.exists():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    if not isinstance(loaded, dict):
        return []
    competitors_raw = loaded.get("competitors")
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

        graph = getattr(request.app.state, "compiled_graph", None)
        if graph is None:
            raise APIException(
                status_code=500,
                error_code="GRAPH_NOT_INITIALIZED",
                message="Compiled LangGraph instance is not initialized.",
            )
        graph_state = await graph.ainvoke(
            {
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
            },
            config={"configurable": {"thread_id": run_id}},
        )

        async with session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise APIException(
                    status_code=500,
                    error_code="RUN_NOT_FOUND",
                    message=f"run_id={run_id} should exist after creation",
                )
            run_status = str(graph_state.get("status", "completed"))
            run.status = run_status if run_status in {"completed", "degraded"} else "completed"
            run.finished_at = datetime.now(timezone.utc)
            final_competitors = graph_state.get("competitors")
            if isinstance(final_competitors, list) and final_competitors:
                run.competitors = final_competitors
            await session.commit()
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.RUN_FINISH,
            payload=_build_run_finish_payload(run_id=run_id, status=run.status),
        )
        task = asyncio.create_task(
            run_skill_curator_for_run(run_id=run_id, domain_hint=payload.domain_hint),
            name=f"skill_curator_{run_id}",
        )
        _register_background_task(request, task)
        log.info("api.run.create.finish", status=run.status)

    return RunCreateResponse(
        run_id=run_id,
        status=run.status,
        message="Supervisor loop run persisted.",
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
