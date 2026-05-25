from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.report import Report
from models.step import Step
from schemas.ids import make_id
from schemas.supervisor import Write
from service.llm import (
    WRITER_ALLOWED_SECTION_IDS,
    WRITER_SYSTEM_PROMPT,
    build_writer_fallback_user_prompt,
    build_writer_user_prompt,
)
from service.llm.client import get_llm_client
from utils.log_node import log_node


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_analyst_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {
            "summary": "",
            "insights": [],
            "risk_flags": [],
            "recommended_sections": [],
        }

    summary_raw = payload.get("summary")
    summary = summary_raw.strip() if isinstance(summary_raw, str) else ""

    insights_raw = payload.get("insights")
    insights: list[dict[str, object]] = []
    if isinstance(insights_raw, list):
        for item in insights_raw:
            if not isinstance(item, dict):
                continue
            dimension_raw = item.get("dimension")
            finding_raw = item.get("finding")
            confidence_raw = item.get("confidence")
            evidence_ids_raw = item.get("evidence_ids")
            if (
                not isinstance(dimension_raw, str)
                or dimension_raw not in WRITER_ALLOWED_SECTION_IDS
                or not isinstance(finding_raw, str)
                or not finding_raw.strip()
                or not isinstance(evidence_ids_raw, list)
            ):
                continue
            evidence_ids = [item for item in evidence_ids_raw if isinstance(item, str)]
            confidence = (
                confidence_raw
                if isinstance(confidence_raw, str) and confidence_raw in {"high", "medium", "low"}
                else "medium"
            )
            insights.append(
                {
                    "dimension": dimension_raw,
                    "finding": finding_raw.strip(),
                    "confidence": confidence,
                    "evidence_ids": evidence_ids,
                }
            )

    risk_flags_raw = payload.get("risk_flags")
    risk_flags = (
        [item for item in risk_flags_raw if isinstance(item, str)]
        if isinstance(risk_flags_raw, list)
        else []
    )
    recommended_sections_raw = payload.get("recommended_sections")
    if isinstance(recommended_sections_raw, list):
        recommended_sections = [
            item for item in recommended_sections_raw if isinstance(item, str) and item in WRITER_ALLOWED_SECTION_IDS
        ]
    else:
        recommended_sections = []

    return {
        "summary": summary,
        "insights": insights,
        "risk_flags": risk_flags,
        "recommended_sections": _stable_unique(recommended_sections),
    }


async def _load_writer_inputs(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> tuple[list[EvidenceRecord], dict[str, object]]:
    async with session_factory() as session:
        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()
        analyst_step = (
            await session.execute(
                select(Step)
                .where(
                    Step.run_id == run_id,
                    Step.agent_name == "analyst",
                    Step.status == "completed",
                )
                .order_by(Step.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

    if analyst_step is None:
        return evidence_rows, _normalize_analyst_payload({})
    analyst_payload_raw = analyst_step.payload.get("analysis_payload")
    return evidence_rows, _normalize_analyst_payload(analyst_payload_raw)


def _build_evidence_briefs(evidence_rows: list[EvidenceRecord]) -> list[dict[str, str]]:
    briefs: list[dict[str, str]] = []
    for row in evidence_rows:
        span = row.span if isinstance(row.span, dict) else {}
        dimension_raw = span.get("dimension")
        competitor_id_raw = span.get("competitor_id")
        briefs.append(
            {
                "evidence_id": row.id,
                "dimension": dimension_raw if isinstance(dimension_raw, str) else "unknown",
                "competitor_id": competitor_id_raw if isinstance(competitor_id_raw, str) else "unknown",
                "quote_preview": row.sanitized_text[:220],
                "source_title": row.source_title or "",
                "source_url": row.source_url or "",
            }
        )
    return briefs


def _build_insight_briefs(
    *,
    analyst_payload: dict[str, object],
    allowed_evidence_ids: set[str],
) -> list[dict[str, object]]:
    insight_briefs: list[dict[str, object]] = []
    insights_raw = analyst_payload.get("insights")
    if not isinstance(insights_raw, list):
        return insight_briefs
    for index, item in enumerate(insights_raw):
        if not isinstance(item, dict):
            continue
        dimension_raw = item.get("dimension")
        finding_raw = item.get("finding")
        confidence_raw = item.get("confidence")
        evidence_ids_raw = item.get("evidence_ids")
        if (
            not isinstance(dimension_raw, str)
            or dimension_raw not in WRITER_ALLOWED_SECTION_IDS
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
        insight_briefs.append(
            {
                "insight_id": f"insight_{index + 1}",
                "dimension": dimension_raw,
                "finding": finding_raw.strip(),
                "confidence": confidence_raw if isinstance(confidence_raw, str) else "medium",
                "evidence_ids": evidence_ids,
            }
        )
    return insight_briefs


def _resolve_target_sections(
    *,
    requested_sections: list[str] | None,
    recommended_sections: list[str],
) -> list[str]:
    targets: list[str] = []
    if requested_sections:
        targets.extend(
            section_id
            for section_id in requested_sections
            if isinstance(section_id, str) and section_id in WRITER_ALLOWED_SECTION_IDS
        )
    if not targets:
        targets.extend(section_id for section_id in recommended_sections if section_id in WRITER_ALLOWED_SECTION_IDS)
    if not targets:
        targets = ["feature", "pricing", "user_feedback"]
    return _stable_unique(targets)


def _normalize_writer_output(
    *,
    content: dict[str, object],
    template_id: str,
    target_sections: list[str],
    allowed_evidence_ids: set[str],
    allowed_insight_ids: set[str],
    default_risk_callouts: list[str],
) -> dict[str, object] | None:
    title_raw = content.get("title")
    executive_summary_raw = content.get("executive_summary")
    template_id_raw = content.get("template_id")
    sections_raw = content.get("sections")
    if (
        not isinstance(title_raw, str)
        or not title_raw.strip()
        or not isinstance(executive_summary_raw, str)
        or not executive_summary_raw.strip()
        or not isinstance(template_id_raw, str)
        or template_id_raw != template_id
        or not isinstance(sections_raw, list)
    ):
        return None

    normalized_sections: list[dict[str, object]] = []
    for item in sections_raw:
        if not isinstance(item, dict):
            continue
        section_id_raw = item.get("section_id")
        section_title_raw = item.get("title")
        content_markdown_raw = item.get("content_markdown")
        evidence_refs_raw = item.get("evidence_refs")
        insight_refs_raw = item.get("insight_refs")
        if (
            not isinstance(section_id_raw, str)
            or section_id_raw not in WRITER_ALLOWED_SECTION_IDS
            or not isinstance(section_title_raw, str)
            or not section_title_raw.strip()
            or not isinstance(content_markdown_raw, str)
            or len(content_markdown_raw.strip()) < 60
            or not isinstance(evidence_refs_raw, list)
        ):
            continue
        evidence_refs = [
            evidence_id
            for evidence_id in evidence_refs_raw
            if isinstance(evidence_id, str) and evidence_id in allowed_evidence_ids
        ]
        if not evidence_refs:
            continue
        if isinstance(insight_refs_raw, list):
            insight_refs = [
                insight_id
                for insight_id in insight_refs_raw
                if isinstance(insight_id, str) and insight_id in allowed_insight_ids
            ]
        else:
            insight_refs = []
        normalized_sections.append(
            {
                "section_id": section_id_raw,
                "title": section_title_raw.strip(),
                "content_markdown": content_markdown_raw.strip(),
                "evidence_refs": _stable_unique(evidence_refs),
                "insight_refs": _stable_unique(insight_refs),
            }
        )

    if not normalized_sections:
        return None
    normalized_ids = {section["section_id"] for section in normalized_sections}
    if target_sections and not all(section_id in normalized_ids for section_id in target_sections):
        return None

    risk_callouts_raw = content.get("risk_callouts")
    if isinstance(risk_callouts_raw, list):
        risk_callouts = [item for item in risk_callouts_raw if isinstance(item, str)]
    else:
        risk_callouts = default_risk_callouts

    return {
        "template_id": template_id,
        "title": title_raw.strip(),
        "executive_summary": executive_summary_raw.strip(),
        "sections": normalized_sections,
        "risk_callouts": risk_callouts,
    }


def _build_fallback_report(
    *,
    template_id: str,
    target_sections: list[str],
    evidence_ids: list[str],
    analyst_summary: str,
    insight_briefs: list[dict[str, object]],
    risk_flags: list[str],
) -> dict[str, object]:
    section_title_map = {
        "feature": "Feature Comparison",
        "pricing": "Pricing Strategy",
        "user_feedback": "User Feedback Signals",
        "differentiation": "Differentiation",
        "swot": "SWOT Snapshot",
    }
    sections: list[dict[str, object]] = []
    for section_id in target_sections:
        related_insights = [
            insight
            for insight in insight_briefs
            if isinstance(insight.get("dimension"), str) and insight["dimension"] == section_id
        ]
        if not related_insights:
            related_insights = insight_briefs[:2]
        if related_insights:
            insight_refs = [
                item["insight_id"]
                for item in related_insights
                if isinstance(item.get("insight_id"), str)
            ]
        else:
            insight_refs = []

        evidence_refs: list[str] = []
        for insight in related_insights:
            evidence_ids_raw = insight.get("evidence_ids")
            if not isinstance(evidence_ids_raw, list):
                continue
            for evidence_id in evidence_ids_raw:
                if isinstance(evidence_id, str):
                    evidence_refs.append(evidence_id)
        if not evidence_refs:
            evidence_refs = evidence_ids[:2]

        if related_insights:
            insight_lines = [
                f"- {item['finding']} (confidence: {item.get('confidence', 'medium')})"
                for item in related_insights
                if isinstance(item.get("finding"), str)
            ]
        else:
            insight_lines = [
                "- Analyst insight is pending; this section summarizes available evidence for follow-up."
            ]
        content_markdown = (
            "This section is generated in fallback mode based on available analyst outputs "
            "and evidence records to keep the report usable for QA and reviewer traceability.\n\n"
            + "\n".join(insight_lines)
        )
        sections.append(
            {
                "section_id": section_id,
                "title": section_title_map.get(section_id, section_id.title()),
                "content_markdown": content_markdown,
                "evidence_refs": _stable_unique([item for item in evidence_refs if item in evidence_ids]),
                "insight_refs": _stable_unique(insight_refs),
            }
        )

    if not sections:
        sections.append(
            {
                "section_id": "feature",
                "title": "Feature Comparison",
                "content_markdown": (
                    "Fallback writer generated a minimal section because no valid target sections were resolved "
                    "from request/recommended inputs."
                ),
                "evidence_refs": evidence_ids[:1],
                "insight_refs": [],
            }
        )

    summary = analyst_summary.strip() if analyst_summary.strip() else "Fallback writer summary from analyst context."
    return {
        "template_id": template_id,
        "title": "RivalLens Competitive Battlecard",
        "executive_summary": summary,
        "sections": sections,
        "risk_callouts": risk_flags or ["writer_fallback_mode"],
    }


def _render_report_markdown(report_content: dict[str, object]) -> str:
    title_raw = report_content.get("title")
    title = title_raw.strip() if isinstance(title_raw, str) and title_raw.strip() else "RivalLens Report"
    executive_summary_raw = report_content.get("executive_summary")
    executive_summary = (
        executive_summary_raw.strip()
        if isinstance(executive_summary_raw, str) and executive_summary_raw.strip()
        else "No executive summary."
    )
    markdown_lines = [
        f"# {title}",
        "",
        "## Executive Summary",
        executive_summary,
        "",
    ]
    sections_raw = report_content.get("sections")
    if isinstance(sections_raw, list):
        for section in sections_raw:
            if not isinstance(section, dict):
                continue
            section_title_raw = section.get("title")
            section_title = (
                section_title_raw.strip()
                if isinstance(section_title_raw, str) and section_title_raw.strip()
                else "Section"
            )
            section_body_raw = section.get("content_markdown")
            section_body = (
                section_body_raw.strip()
                if isinstance(section_body_raw, str) and section_body_raw.strip()
                else "No content."
            )
            markdown_lines.extend(
                [
                    f"## {section_title}",
                    section_body,
                ]
            )
            evidence_refs_raw = section.get("evidence_refs")
            if isinstance(evidence_refs_raw, list):
                evidence_refs = [item for item in evidence_refs_raw if isinstance(item, str)]
            else:
                evidence_refs = []
            if evidence_refs:
                markdown_lines.append(
                    "Evidence: " + ", ".join(f"[{evidence_id}]" for evidence_id in evidence_refs)
                )
            insight_refs_raw = section.get("insight_refs")
            if isinstance(insight_refs_raw, list):
                insight_refs = [item for item in insight_refs_raw if isinstance(item, str)]
            else:
                insight_refs = []
            if insight_refs:
                markdown_lines.append("Insights: " + ", ".join(insight_refs))
            markdown_lines.append("")

    risk_callouts_raw = report_content.get("risk_callouts")
    if isinstance(risk_callouts_raw, list):
        risk_callouts = [item for item in risk_callouts_raw if isinstance(item, str)]
    else:
        risk_callouts = []
    if risk_callouts:
        markdown_lines.append("## Risk Callouts")
        for item in risk_callouts:
            markdown_lines.append(f"- {item}")
        markdown_lines.append("")

    return "\n".join(markdown_lines).strip() + "\n"


@log_node("writer")
async def writer_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for writer node.")

    session_factory = _require_session_factory(state)
    request = Write.model_validate(state.get("pending_tool_args", {}))
    step_id = make_id("step_")
    report_id = f"report_{uuid4().hex[:12]}"
    evidence_rows, analyst_payload = await _load_writer_inputs(
        session_factory=session_factory,
        run_id=run_id,
    )
    evidence_briefs = _build_evidence_briefs(evidence_rows)
    allowed_evidence_ids = {item["evidence_id"] for item in evidence_briefs}
    insight_briefs = _build_insight_briefs(
        analyst_payload=analyst_payload,
        allowed_evidence_ids=allowed_evidence_ids,
    )
    allowed_insight_ids = {
        item["insight_id"]
        for item in insight_briefs
        if isinstance(item.get("insight_id"), str)
    }
    recommended_sections_raw = analyst_payload.get("recommended_sections")
    if isinstance(recommended_sections_raw, list):
        recommended_sections = [
            item
            for item in recommended_sections_raw
            if isinstance(item, str) and item in WRITER_ALLOWED_SECTION_IDS
        ]
    else:
        recommended_sections = []
    target_sections = _resolve_target_sections(
        requested_sections=request.sections,
        recommended_sections=recommended_sections,
    )
    analyst_summary_raw = analyst_payload.get("summary")
    analyst_summary = analyst_summary_raw if isinstance(analyst_summary_raw, str) else ""
    risk_flags_raw = analyst_payload.get("risk_flags")
    risk_flags = [item for item in risk_flags_raw if isinstance(item, str)] if isinstance(risk_flags_raw, list) else []

    llm_response = await get_llm_client().complete_json(
        model_slot="writer",
        system_prompt=WRITER_SYSTEM_PROMPT,
        user_prompt=build_writer_user_prompt(
            user_query=str(state.get("user_query", "")),
            template_id=request.template_id,
            requested_sections=target_sections,
            competitors=list(state.get("competitors", [])),
            evidence_briefs=evidence_briefs,
            analyst_summary=analyst_summary,
            analyst_insights=insight_briefs,
            risk_flags=risk_flags,
            recommended_sections=recommended_sections,
        ),
        fallback_system_prompt=WRITER_SYSTEM_PROMPT,
        fallback_user_prompt=build_writer_fallback_user_prompt(
            template_id=request.template_id,
            requested_sections=target_sections,
            evidence_ids=sorted(allowed_evidence_ids),
            analyst_summary=analyst_summary,
        ),
    )

    writer_schema_error: str | None = None
    normalized = _normalize_writer_output(
        content=llm_response.content,
        template_id=request.template_id,
        target_sections=target_sections,
        allowed_evidence_ids=allowed_evidence_ids,
        allowed_insight_ids=allowed_insight_ids,
        default_risk_callouts=risk_flags,
    )
    writer_mode: Literal["llm", "fallback"]
    if llm_response.error is None and normalized is not None:
        writer_mode = "llm"
        report_content = normalized
        fallback_reason = llm_response.fallback_reason
    else:
        writer_mode = "fallback"
        if llm_response.error is None and normalized is None:
            writer_schema_error = "writer_output_schema_invalid"
        fallback_reason = llm_response.error or writer_schema_error
        report_content = _build_fallback_report(
            template_id=request.template_id,
            target_sections=target_sections,
            evidence_ids=sorted(allowed_evidence_ids),
            analyst_summary=analyst_summary,
            insight_briefs=insight_briefs,
            risk_flags=risk_flags,
        )
    markdown = _render_report_markdown(report_content)
    llm_call_error = llm_response.error or writer_schema_error
    llm_call_error_trimmed = llm_call_error[:2000] if llm_call_error is not None else None
    section_count = (
        len(report_content["sections"])
        if isinstance(report_content.get("sections"), list)
        else 0
    )
    evidence_ref_count = 0
    sections_raw = report_content.get("sections")
    if isinstance(sections_raw, list):
        for section in sections_raw:
            if not isinstance(section, dict):
                continue
            section_refs = section.get("evidence_refs")
            if isinstance(section_refs, list):
                evidence_ref_count += len([item for item in section_refs if isinstance(item, str)])

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="writer",
            status="running",
            retry_count=0,
            payload={
                **request.model_dump(),
                "writer_mode": writer_mode,
                "report_title": report_content.get("title"),
                "section_count": section_count,
                "evidence_ref_count": evidence_ref_count,
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
            Report(
                report_id=report_id,
                run_id=run_id,
                status="completed",
                content_json=report_content,
                content_markdown=markdown,
            )
        )
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="report_draft",
                uri=f"memory://report/{run_id}/{report_id}",
                sha256=None,
                size_bytes=None,
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    return {
        "report_draft_done": True,
        "pending_tool_args": {},
        "pending_review_target_step_id": step_id,
        "status": "running",
    }
