from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from agents.state import AgentState
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.step import Step
from schemas.agent_outputs import AnalystOutput
from schemas.contracts import normalize_dimension_or_none
from schemas.ids import make_id
from schemas.supervisor import Analyze
from service.comparison import persist_comparisons_for_step
from service.event_bus import RunEventType, emit_run_event
from service.conclusion import persist_comparison_conclusions_for_step, persist_conclusions_for_step
from service.llm import (
    ANALYST_SYSTEM_PROMPT,
    build_analyst_fallback_user_prompt,
    build_analyst_repair_user_prompt,
    build_analyst_user_prompt,
)
from service.llm.harness import complete_structured
from service.llm.records import build_llm_call_record
from utils.log_node import log_node
from utils.logger import get_logger

log = get_logger("agents.analyst")


def _resolve_focus_dimensions(request: Analyze) -> list[str]:
    if request.focus_dimensions:
        return sorted(set(request.focus_dimensions))
    return []


def _build_evidence_briefs(
    *,
    evidence_rows: list[EvidenceRecord],
    focus_dimensions: list[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    dropped_reasons: dict[str, int] = {}
    briefs: list[dict[str, object]] = []
    for row in evidence_rows:
        span = row.span if isinstance(row.span, dict) else {}
        dimension_raw = span.get("dimension")
        dimension, drop_reason = normalize_dimension_or_none(
            dimension_raw,
            allowed=focus_dimensions,
        )
        if drop_reason is not None:
            dropped_reasons[drop_reason] = dropped_reasons.get(drop_reason, 0) + 1
        competitor_raw = span.get("competitor_id")
        competitor_id = competitor_raw if isinstance(competitor_raw, str) else "unknown"
        authority_raw = span.get("source_authority")
        briefs.append(
            {
                "evidence_id": row.id,
                "dimension": dimension,
                "competitor_id": competitor_id,
                "quote_preview": row.sanitized_text[:220],
                "source_title": row.source_title or "",
                "source_url": row.source_url or "",
                "source_type": row.source_type or "",
                "source_authority": authority_raw if isinstance(authority_raw, str) else "third_party",
            }
        )
    return (
        briefs,
        {
            "count": sum(dropped_reasons.values()),
            "reasons": dropped_reasons,
        },
    )


@log_node("analyst")
async def analyst_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for analyst node.")

    session_factory = get_session_factory()
    request = Analyze.model_validate(state.get("pending_tool_args", {}))
    focus_dimensions = _resolve_focus_dimensions(request)
    user_query = str(state.get("user_query", ""))
    competitors = list(state.get("competitors", []))
    step_id = make_id("step_")
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_START,
        step_id=step_id,
        payload={
            "agent_name": "analyst",
            "focus_dimensions": focus_dimensions,
        },
    )

    async with session_factory() as session:
        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()

    evidence_briefs, dropped_dimensions = _build_evidence_briefs(
        evidence_rows=evidence_rows,
        focus_dimensions=focus_dimensions,
    )
    if not focus_dimensions:
        focus_dimensions = sorted(
            {
                item["dimension"]
                for item in evidence_briefs
                if isinstance(item.get("dimension"), str) and item["dimension"]
            }
        )
        if not focus_dimensions:
            # Empty-evidence fallback is intentionally broader than the default intake focus.
            focus_dimensions = ["general", "feature", "pricing"]
    allowed_evidence_ids = {item["evidence_id"] for item in evidence_briefs}
    allowed_dimensions = set(focus_dimensions)
    dropped_insight_dimensions: dict[str, int] = {}
    user_prompt = build_analyst_user_prompt(
        user_query=user_query,
        competitors=competitors,
        focus_dimensions=focus_dimensions,
        evidence_briefs=evidence_briefs,
    )
    fallback_prompt = build_analyst_fallback_user_prompt(
        competitors=competitors,
        focus_dimensions=focus_dimensions,
        evidence_ids=sorted(allowed_evidence_ids),
    )
    harness_result = await complete_structured(
        model_slot="summarization",
        system_prompt=ANALYST_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_model=AnalystOutput,
        parser=lambda content: AnalystOutput.parse_llm_content(
            content,
            allowed_evidence_ids=allowed_evidence_ids,
            allowed_dimensions=allowed_dimensions,
            competitors={item for item in competitors if isinstance(item, str) and item},
            dropped_dimensions=dropped_insight_dimensions,
        ),
        fallback_system_prompt=ANALYST_SYSTEM_PROMPT,
        fallback_user_prompt=fallback_prompt,
        repair_user_prompt_builder=lambda errors: build_analyst_repair_user_prompt(
            validation_errors=errors,
            focus_dimensions=focus_dimensions,
            evidence_ids=sorted(allowed_evidence_ids),
        ),
        log_event="analyst.harness.finish",
    )
    llm_response = harness_result.llm_response

    analysis_schema_error: str | None = None
    if harness_result.value is not None:
        analysis_mode = "llm"
        analysis_output = harness_result.value
        fallback_reason = llm_response.fallback_reason
    else:
        analysis_mode = "fallback"
        if llm_response.error is None:
            analysis_schema_error = harness_result.schema_error or "analyst_output_schema_invalid"
        fallback_reason = llm_response.error or analysis_schema_error
        analysis_output = AnalystOutput.build_fallback(
            focus_dimensions=focus_dimensions,
            evidence_briefs=evidence_briefs,
        )
    analysis_result = analysis_output.to_persisted_dict()
    analysis_insights = (
        [item for item in analysis_result["insights"] if isinstance(item, dict)]
        if isinstance(analysis_result.get("insights"), list)
        else []
    )
    analysis_risk_flags = (
        [item for item in analysis_result["risk_flags"] if isinstance(item, str)]
        if isinstance(analysis_result.get("risk_flags"), list)
        else []
    )
    analysis_comparisons = (
        [item for item in analysis_result["comparisons"] if isinstance(item, dict)]
        if isinstance(analysis_result.get("comparisons"), list)
        else []
    )
    evidence_lookup = {row.id: row for row in evidence_rows}

    llm_call_error = llm_response.error or analysis_schema_error
    async with session_factory() as session:
        step_payload: dict[str, object] = {
            **request.model_dump(),
            "focus_dimensions": focus_dimensions,
            "analysis_mode": analysis_mode,
            "analysis_payload": analysis_result,
            "analysis_summary": analysis_result["summary"],
            "insight_count": len(
                analysis_result["insights"] if isinstance(analysis_result["insights"], list) else []
            ),
            "dropped_dimensions": dropped_dimensions,
            "dropped_insight_dimensions": {
                "count": sum(dropped_insight_dimensions.values()),
                "reasons": dict(dropped_insight_dimensions),
            },
            "fallback_reason": fallback_reason,
            "llm_provider": llm_response.provider,
            "llm_prompt_preview": llm_response.prompt_preview,
            "llm_fallback_used": llm_response.fallback_used,
            "llm_fallback_reason": llm_response.fallback_reason,
        }
        log.info(
            "analyst.dimension_drops",
            run_id=run_id,
            step_id=step_id,
            dropped_dimensions=dropped_dimensions,
            dropped_insight_dimensions={
                "count": sum(dropped_insight_dimensions.values()),
                "reasons": dict(dropped_insight_dimensions),
            },
        )
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="analyst",
            status="running",
            retry_count=0,
            payload=step_payload,
        )
        session.add(step)
        await session.flush()
        session.add(
            build_llm_call_record(
                step_id=step_id,
                response=llm_response,
                error=llm_call_error,
            )
        )
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="analysis_result",
                uri=f"memory://analysis/{run_id}/{step_id}",
                sha256=None,
                size_bytes=None,
            )
        )
        conclusions_persist_error: str | None = None
        persisted_conclusion_count = 0
        persisted_insight_conclusion_count = 0
        persisted_comparison_conclusion_count = 0
        covered_conclusion_sections: set[str] = set()
        try:
            async with session.begin_nested():
                conclusion_records = await persist_conclusions_for_step(
                    session=session,
                    run_id=run_id,
                    step_id=step_id,
                    insights=analysis_insights,
                    evidence_lookup=evidence_lookup,
                    risk_flags=analysis_risk_flags,
                )
                await session.flush()
                persisted_insight_conclusion_count = len(conclusion_records)
                covered_conclusion_sections = {record.section for record in conclusion_records}
        except SQLAlchemyError as exc:
            conclusions_persist_error = str(exc)[:2000]
            log.info(
                "analyst.conclusions.persist_fail",
                run_id=run_id,
                step_id=step_id,
                error=conclusions_persist_error,
            )
        comparison_conclusions_persist_error: str | None = None
        try:
            async with session.begin_nested():
                comparison_conclusion_records = await persist_comparison_conclusions_for_step(
                    session=session,
                    run_id=run_id,
                    step_id=step_id,
                    comparisons=analysis_comparisons,
                    evidence_lookup=evidence_lookup,
                    competitors=[item for item in competitors if isinstance(item, str)],
                    covered_sections=covered_conclusion_sections,
                    risk_flags=analysis_risk_flags,
                )
                await session.flush()
                persisted_comparison_conclusion_count = len(comparison_conclusion_records)
        except SQLAlchemyError as exc:
            comparison_conclusions_persist_error = str(exc)[:2000]
            log.info(
                "analyst.comparison_conclusions.persist_fail",
                run_id=run_id,
                step_id=step_id,
                error=comparison_conclusions_persist_error,
            )
        persisted_conclusion_count = (
            persisted_insight_conclusion_count + persisted_comparison_conclusion_count
        )
        step.payload = {
            **step.payload,
            "conclusions_persisted_count": persisted_conclusion_count,
            "insight_conclusions_persisted_count": persisted_insight_conclusion_count,
            "comparison_conclusions_backfilled_count": persisted_comparison_conclusion_count,
        }
        if conclusions_persist_error is not None:
            step.payload = {
                **step.payload,
                "conclusions_persist_error": conclusions_persist_error,
            }
        if comparison_conclusions_persist_error is not None:
            step.payload = {
                **step.payload,
                "comparison_conclusions_persist_error": comparison_conclusions_persist_error,
            }
        comparisons_persist_error: str | None = None
        persisted_comparison_count = 0
        try:
            async with session.begin_nested():
                comparison_records = await persist_comparisons_for_step(
                    session=session,
                    run_id=run_id,
                    step_id=step_id,
                    comparisons=analysis_comparisons,
                    evidence_lookup=evidence_lookup,
                    competitors=[item for item in competitors if isinstance(item, str)],
                )
                await session.flush()
                persisted_comparison_count = len(comparison_records)
        except (SQLAlchemyError, ValueError) as exc:
            comparisons_persist_error = str(exc)[:2000]
            log.info(
                "analyst.comparisons.persist_fail",
                run_id=run_id,
                step_id=step_id,
                error=comparisons_persist_error,
            )
        step.payload = {
            **step.payload,
            "comparison_count": persisted_comparison_count,
        }
        if comparisons_persist_error is not None:
            step.payload = {
                **step.payload,
                "comparisons_persist_error": comparisons_persist_error,
            }
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={
            "agent_name": "analyst",
            "status": "completed",
            "analysis_mode": analysis_mode,
            "insight_count": len(analysis_insights),
        },
    )

    return {
        "analysis_done": True,
        "pending_tool_args": {},
        "last_completed_node": "analyst",
        "status": "running",
    }
