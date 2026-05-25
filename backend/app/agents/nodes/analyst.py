from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.step import Step
from schemas.ids import make_id
from schemas.supervisor import Analyze
from service.llm import (
    ANALYST_SYSTEM_PROMPT,
    SUPERVISOR_ALLOWED_DIMENSIONS,
    build_analyst_fallback_user_prompt,
    build_analyst_user_prompt,
)
from service.llm.client import get_llm_client
from utils.log_node import log_node


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _resolve_focus_dimensions(request: Analyze) -> list[str]:
    if request.focus_dimensions:
        return list(request.focus_dimensions)
    return list(SUPERVISOR_ALLOWED_DIMENSIONS)


def _build_evidence_briefs(
    *,
    evidence_rows: list[EvidenceRecord],
    focus_dimensions: list[str],
) -> list[dict[str, str]]:
    allowed_dimensions = set(focus_dimensions)
    briefs: list[dict[str, str]] = []
    for row in evidence_rows:
        span = row.span if isinstance(row.span, dict) else {}
        dimension_raw = span.get("dimension")
        dimension = dimension_raw if isinstance(dimension_raw, str) else "unknown"
        if dimension not in allowed_dimensions:
            continue
        competitor_raw = span.get("competitor_id")
        competitor_id = competitor_raw if isinstance(competitor_raw, str) else "unknown"
        briefs.append(
            {
                "evidence_id": row.id,
                "dimension": dimension,
                "competitor_id": competitor_id,
                "quote_preview": row.sanitized_text[:220],
                "source_title": row.source_title or "",
                "source_url": row.source_url or "",
            }
        )
    return briefs


def _normalize_analysis_output(
    *,
    content: dict[str, object],
    allowed_evidence_ids: set[str],
    allowed_dimensions: set[str],
) -> dict[str, object] | None:
    summary_raw = content.get("summary")
    if not isinstance(summary_raw, str) or not summary_raw.strip():
        return None

    insights_raw = content.get("insights")
    if not isinstance(insights_raw, list):
        return None

    insights: list[dict[str, object]] = []
    for item in insights_raw:
        if not isinstance(item, dict):
            continue
        dimension_raw = item.get("dimension")
        finding_raw = item.get("finding")
        evidence_ids_raw = item.get("evidence_ids")
        confidence_raw = item.get("confidence")
        if (
            not isinstance(dimension_raw, str)
            or dimension_raw not in allowed_dimensions
            or not isinstance(finding_raw, str)
            or not finding_raw.strip()
            or not isinstance(evidence_ids_raw, list)
        ):
            continue
        evidence_ids = [
            evidence_id
            for evidence_id in evidence_ids_raw
            if isinstance(evidence_id, str) and evidence_id in allowed_evidence_ids
        ]
        if not evidence_ids:
            continue
        confidence = (
            confidence_raw
            if isinstance(confidence_raw, str) and confidence_raw in {"high", "medium", "low"}
            else "medium"
        )
        insights.append(
            {
                "dimension": dimension_raw,
                "finding": finding_raw.strip(),
                "evidence_ids": evidence_ids,
                "confidence": confidence,
            }
        )

    if not insights:
        return None

    risk_flags_raw = content.get("risk_flags")
    risk_flags = (
        [item for item in risk_flags_raw if isinstance(item, str)]
        if isinstance(risk_flags_raw, list)
        else []
    )
    recommended_sections_raw = content.get("recommended_sections")
    if isinstance(recommended_sections_raw, list):
        recommended_sections = [item for item in recommended_sections_raw if isinstance(item, str)]
    else:
        recommended_sections = sorted({item["dimension"] for item in insights})

    return {
        "summary": summary_raw.strip(),
        "insights": insights,
        "risk_flags": risk_flags,
        "recommended_sections": recommended_sections,
    }


def _build_fallback_analysis(
    *,
    focus_dimensions: list[str],
    evidence_briefs: list[dict[str, str]],
) -> dict[str, object]:
    if evidence_briefs:
        first = evidence_briefs[0]
        summary = (
            f"Fallback analysis generated from {len(evidence_briefs)} evidence snippets "
            f"across {len(focus_dimensions)} dimensions."
        )
        insight = {
            "dimension": first["dimension"],
            "finding": (
                f"Preliminary signal from {first['competitor_id']} on {first['dimension']} "
                "requires deeper analyst iteration."
            ),
            "evidence_ids": [first["evidence_id"]],
            "confidence": "low",
        }
    else:
        summary = "Fallback analysis generated without evidence; analyst should re-run after research recovers."
        first_dimension = focus_dimensions[0] if focus_dimensions else "feature"
        insight = {
            "dimension": first_dimension,
            "finding": "No evidence available for analyst pass.",
            "evidence_ids": [],
            "confidence": "low",
        }

    return {
        "summary": summary,
        "insights": [insight],
        "risk_flags": ["analyst_fallback_mode"],
        "recommended_sections": focus_dimensions,
    }


@log_node("analyst")
async def analyst_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for analyst node.")

    session_factory = _require_session_factory(state)
    request = Analyze.model_validate(state.get("pending_tool_args", {}))
    focus_dimensions = _resolve_focus_dimensions(request)
    user_query = str(state.get("user_query", ""))
    competitors = list(state.get("competitors", []))
    step_id = make_id("step_")

    async with session_factory() as session:
        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()

    evidence_briefs = _build_evidence_briefs(
        evidence_rows=evidence_rows,
        focus_dimensions=focus_dimensions,
    )
    allowed_evidence_ids = {item["evidence_id"] for item in evidence_briefs}
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
    llm_response = await get_llm_client().complete_json(
        model_slot="summarization",
        system_prompt=ANALYST_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        fallback_system_prompt=ANALYST_SYSTEM_PROMPT,
        fallback_user_prompt=fallback_prompt,
    )

    analysis_schema_error: str | None = None
    normalized = _normalize_analysis_output(
        content=llm_response.content,
        allowed_evidence_ids=allowed_evidence_ids,
        allowed_dimensions=set(focus_dimensions),
    )
    if llm_response.error is None and normalized is not None:
        analysis_mode = "llm"
        analysis_result: dict[str, object] = normalized
        fallback_reason = llm_response.fallback_reason
    else:
        analysis_mode = "fallback"
        if llm_response.error is None and normalized is None:
            analysis_schema_error = "analyst_output_schema_invalid"
        fallback_reason = llm_response.error or analysis_schema_error
        analysis_result = _build_fallback_analysis(
            focus_dimensions=focus_dimensions,
            evidence_briefs=evidence_briefs,
        )

    llm_call_error = llm_response.error or analysis_schema_error
    llm_call_error_trimmed = llm_call_error[:2000] if llm_call_error is not None else None

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="analyst",
            status="running",
            retry_count=0,
            payload={
                **request.model_dump(),
                "focus_dimensions": focus_dimensions,
                "analysis_mode": analysis_mode,
                "analysis_payload": analysis_result,
                "analysis_summary": analysis_result["summary"],
                "insight_count": len(
                    analysis_result["insights"] if isinstance(analysis_result["insights"], list) else []
                ),
                "fallback_reason": fallback_reason,
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
                step_id=step_id,
                model_slot=llm_response.model_slot,
                provider=llm_response.provider,
                model_name=llm_response.model_name,
                prompt_hash=llm_response.prompt_hash,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                latency_ms=llm_response.latency_ms,
                error=llm_call_error_trimmed,
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
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    return {
        "analysis_done": True,
        "pending_tool_args": {},
        "last_completed_node": "analyst",
        "status": "running",
    }
