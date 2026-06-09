from __future__ import annotations

from collections import Counter
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from agents.state_coercion import coerce_intake_draft_or_default
from core.config import settings
from db.engine import get_session_factory
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.report import Report
from models.step import Step
from schemas.agent_outputs import AnalystOutput, WriterExecutionContext, WriterReportOutput
from schemas.ids import make_id
from schemas.supervisor import Write
from schemas.contracts import validate_section_id
from service.comparison import load_comparisons_for_run
from service.event_bus import RunEventType, emit_run_event
from service.conclusion import load_conclusions_for_run
from service.llm import (
    WRITER_SYSTEM_PROMPT,
    build_writer_fallback_user_prompt,
    build_writer_repair_user_prompt,
    build_writer_user_prompt,
)
from service.llm.harness import complete_structured
from service.llm.records import build_llm_call_record
from utils.log_node import log_node
from utils.logger import get_logger

log = get_logger("agents.writer")

BARE_EVIDENCE_ID_PATTERN = re.compile(r"(?<!\[)\b(ev_[A-Za-z0-9_]+)\b(?!\])")
BRACKETED_EVIDENCE_ID_PATTERN = re.compile(r"\[(ev_[A-Za-z0-9_]+)\]")
INSIGHT_ID_PATTERN = re.compile(r"\binsight_[A-Za-z0-9_]+\b")


def _is_valid_section_id(value: str) -> bool:
    try:
        validate_section_id(value)
    except ValueError:
        return False
    return True


def _insight_matches_section(*, insight: dict[str, object], section_id: str) -> bool:
    dimension_raw = insight.get("dimension")
    if not isinstance(dimension_raw, str):
        return False
    return dimension_raw.strip().lower() == section_id


def _select_insights_for_section(
    *,
    section_id: str,
    insight_briefs: list[dict[str, object]],
) -> list[dict[str, object]]:
    matched = [
        insight
        for insight in insight_briefs
        if _insight_matches_section(insight=insight, section_id=section_id)
    ]
    return matched[:3]


def _select_evidence_ids_for_section(
    *,
    section_id: str,
    evidence_briefs: list[dict[str, object]],
    evidence_ids: list[str],
) -> list[str]:
    matched = [
        item["evidence_id"]
        for item in evidence_briefs
        if item.get("evidence_id") in evidence_ids
        and isinstance(item.get("dimension"), str)
        and str(item.get("dimension")).lower() == section_id
    ]
    return _stable_unique(matched)[:3]


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_heading(value: str) -> str:
    collapsed = re.sub(r"[\s:：\-\u2014_]+", "", value.strip().lower())
    return collapsed


def _is_duplicate_executive_summary_section(
    *,
    section_title: str,
    executive_summary_label: str,
) -> bool:
    normalized_section = _normalize_heading(section_title)
    normalized_label = _normalize_heading(executive_summary_label)
    if not normalized_section or not normalized_label:
        return False
    return normalized_section.startswith(normalized_label)


def _format_distribution(
    distribution: Counter[str],
    *,
    empty_label: str,
) -> str:
    if not distribution:
        return empty_label
    ordered = sorted(distribution.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{name}: {count}" for name, count in ordered)


def _build_methodology_section_lines(
    *,
    evidence_briefs: list[dict[str, object]],
    labels: dict[str, str],
) -> list[str]:
    authority_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()
    competitor_stats: dict[str, dict[str, bool]] = {}

    for brief in evidence_briefs:
        authority_raw = brief.get("source_authority")
        source_type_raw = brief.get("source_type")
        competitor_raw = brief.get("competitor_id")

        authority = (
            authority_raw.strip().lower()
            if isinstance(authority_raw, str) and authority_raw.strip()
            else "unknown"
        )
        source_type = (
            source_type_raw.strip().lower()
            if isinstance(source_type_raw, str) and source_type_raw.strip()
            else "unknown"
        )

        authority_counts[authority] += 1
        source_type_counts[source_type] += 1

        if not isinstance(competitor_raw, str):
            continue
        competitor_id = competitor_raw.strip()
        if not competitor_id or competitor_id == "unknown":
            continue
        stats = competitor_stats.setdefault(
            competitor_id,
            {
                "has_official": False,
                "has_pricing_page": False,
            },
        )
        if authority == "official":
            stats["has_official"] = True
        if source_type == "pricing_page":
            stats["has_pricing_page"] = True

    competitor_names = sorted(competitor_stats.keys())
    competitor_list = (
        ", ".join(competitor_names)
        if competitor_names
        else labels["methodology_no_competitors"]
    )
    data_gaps: list[str] = []
    for competitor_id in competitor_names:
        stats = competitor_stats[competitor_id]
        has_official = stats["has_official"]
        has_pricing_page = stats["has_pricing_page"]
        if has_official and has_pricing_page:
            continue
        if not has_official and not has_pricing_page:
            data_gaps.append(
                f"{competitor_id}: {labels['methodology_gap_official_and_pricing']}"
            )
            continue
        if not has_official:
            data_gaps.append(f"{competitor_id}: {labels['methodology_gap_official_only']}")
            continue
        data_gaps.append(f"{competitor_id}: {labels['methodology_gap_pricing_only']}")

    gap_summary = (
        "; ".join(data_gaps)
        if data_gaps
        else labels["methodology_no_data_gaps"]
    )
    generated_on = datetime.now(timezone.utc).date().isoformat()
    return [
        f"- {labels['methodology_generated_on']}: {generated_on}",
        (
            f"- {labels['methodology_competitors']}: "
            f"{len(competitor_names)} ({competitor_list})"
        ),
        f"- {labels['methodology_evidence_total']}: {len(evidence_briefs)}",
        (
            f"- {labels['methodology_authority_distribution']}: "
            f"{_format_distribution(authority_counts, empty_label=labels['methodology_none'])}"
        ),
        (
            f"- {labels['methodology_source_type_distribution']}: "
            f"{_format_distribution(source_type_counts, empty_label=labels['methodology_none'])}"
        ),
        f"- {labels['methodology_data_gaps']}: {gap_summary}",
    ]


def _sanitize_report_markdown_text(
    value: str,
    *,
    allowed_evidence_ids: set[str],
) -> str:
    def replace_bracketed_evidence(match: re.Match[str]) -> str:
        evidence_id = match.group(1)
        if evidence_id in allowed_evidence_ids:
            return f"[{evidence_id}]"
        return ""

    def replace_evidence_id(match: re.Match[str]) -> str:
        evidence_id = match.group(1)
        if evidence_id in allowed_evidence_ids:
            return f"[{evidence_id}]"
        return ""

    sanitized = BRACKETED_EVIDENCE_ID_PATTERN.sub(replace_bracketed_evidence, value)
    sanitized = BARE_EVIDENCE_ID_PATTERN.sub(replace_evidence_id, sanitized)
    sanitized = INSIGHT_ID_PATTERN.sub("", sanitized)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
    sanitized = re.sub(r" ?([,.;:，。；：])", r"\1", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    return sanitized.strip()


def _report_depth_from_state(state: AgentState) -> Literal["quick", "deep"]:
    intake_draft = state.get("intake_draft")
    if isinstance(intake_draft, dict):
        depth_raw = intake_draft.get("report_depth")
    else:
        depth_raw = getattr(intake_draft, "report_depth", None)
    return "deep" if depth_raw == "deep" else "quick"


def _analyst_payload_from_conclusions(
    conclusions: list[dict[str, object]],
    *,
    comparison_rows: list[dict[str, object]] | None = None,
) -> AnalystOutput:
    insights: list[dict[str, object]] = []
    risk_flags: list[str] = []
    recommended_sections: list[str] = []
    for index, item in enumerate(conclusions):
        section_raw = item.get("section")
        claim_raw = item.get("claim")
        confidence_raw = item.get("confidence")
        evidence_ids_raw = item.get("evidence_ids")
        if (
            not isinstance(section_raw, str)
            or not _is_valid_section_id(section_raw)
            or not isinstance(claim_raw, str)
            or not claim_raw.strip()
            or not isinstance(evidence_ids_raw, list)
        ):
            continue
        evidence_ids = [evidence_id for evidence_id in evidence_ids_raw if isinstance(evidence_id, str)]
        if not evidence_ids:
            continue
        confidence = (
            confidence_raw
            if isinstance(confidence_raw, str) and confidence_raw in {"high", "medium", "low"}
            else "medium"
        )
        insights.append(
            {
                "dimension": section_raw,
                "finding": claim_raw.strip(),
                "confidence": confidence,
                "evidence_ids": _stable_unique(evidence_ids),
            }
        )
        recommended_sections.append(section_raw)
        raw_risk_flags = item.get("risk_flags")
        if isinstance(raw_risk_flags, list):
            risk_flags.extend(flag for flag in raw_risk_flags if isinstance(flag, str))

    summary = (
        f"Loaded {len(insights)} persisted conclusions from structured storage."
        if insights
        else ""
    )
    parsed = AnalystOutput.parse_persisted(
        {
            "summary": summary or "Conclusions loaded from structured storage.",
            "insights": insights,
            "comparisons": [
                item for item in (comparison_rows or []) if isinstance(item, dict)
            ],
            "risk_flags": _stable_unique(risk_flags),
            "recommended_sections": _stable_unique(recommended_sections),
        }
    )
    if parsed is None:
        return AnalystOutput.build_fallback(focus_dimensions=[], evidence_briefs=[])
    return parsed


async def _load_writer_inputs(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> tuple[list[EvidenceRecord], AnalystOutput]:
    async with session_factory() as session:
        evidence_rows = (
            await session.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.run_id == run_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        ).scalars().all()
        if settings.WRITER_READ_CONCLUSIONS_FROM_TABLE:
            try:
                conclusion_rows = await load_conclusions_for_run(
                    session=session,
                    run_id=run_id,
                )
            except SQLAlchemyError as exc:
                log.info(
                    "writer.conclusions.fallback_to_json",
                    run_id=run_id,
                    reason="query_error",
                    error=str(exc)[:500],
                )
                conclusion_rows = []
            if conclusion_rows:
                try:
                    comparison_rows = await load_comparisons_for_run(
                        session=session,
                        run_id=run_id,
                    )
                except SQLAlchemyError as exc:
                    log.info(
                        "writer.comparisons.fallback_to_json",
                        run_id=run_id,
                        reason="query_error",
                        error=str(exc)[:500],
                    )
                    comparison_rows = []
                return evidence_rows, _analyst_payload_from_conclusions(
                    conclusion_rows,
                    comparison_rows=comparison_rows,
                )
            log.info(
                "writer.conclusions.fallback_to_json",
                run_id=run_id,
                reason="empty_conclusions",
            )
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

    evidence_briefs = _build_evidence_briefs(evidence_rows)
    if analyst_step is None:
        return evidence_rows, AnalystOutput.build_fallback(
            focus_dimensions=[],
            evidence_briefs=evidence_briefs,
        )
    parsed = AnalystOutput.parse_persisted(analyst_step.payload.get("analysis_payload"))
    if parsed is None:
        return evidence_rows, AnalystOutput.build_fallback(
            focus_dimensions=[],
            evidence_briefs=evidence_briefs,
        )
    return evidence_rows, parsed


def _build_evidence_briefs(evidence_rows: list[EvidenceRecord]) -> list[dict[str, object]]:
    briefs: list[dict[str, object]] = []
    for row in evidence_rows:
        span = row.span if isinstance(row.span, dict) else {}
        dimension_raw = span.get("dimension")
        competitor_id_raw = span.get("competitor_id")
        authority_raw = span.get("source_authority")
        briefs.append(
            {
                "evidence_id": row.id,
                "dimension": dimension_raw if isinstance(dimension_raw, str) else None,
                "competitor_id": competitor_id_raw if isinstance(competitor_id_raw, str) else "unknown",
                "quote_preview": row.sanitized_text[:220],
                "source_title": row.source_title or "",
                "source_url": row.source_url or "",
                "source_type": row.source_type or "",
                "source_authority": authority_raw if isinstance(authority_raw, str) else "third_party",
            }
        )
    return briefs


def _build_insight_briefs(
    *,
    analyst_output: AnalystOutput,
    allowed_evidence_ids: set[str],
) -> list[dict[str, object]]:
    insight_briefs: list[dict[str, object]] = []
    for index, insight in enumerate(analyst_output.insights):
        evidence_ids = [
            evidence_id for evidence_id in insight.evidence_ids if evidence_id in allowed_evidence_ids
        ]
        insight_briefs.append(
            {
                "insight_id": f"insight_{index + 1}",
                "dimension": insight.dimension,
                "finding": insight.finding,
                "confidence": insight.confidence,
                "evidence_ids": evidence_ids,
            }
        )
    return insight_briefs


def _build_comparison_briefs(
    *,
    analyst_output: AnalystOutput,
    allowed_evidence_ids: set[str],
) -> list[dict[str, object]]:
    comparison_briefs: list[dict[str, object]] = []
    for comparison in analyst_output.comparisons:
        cells_payload: list[dict[str, object]] = []
        for cell in comparison.cells:
            grounded_evidence_ids = [
                evidence_id
                for evidence_id in cell.evidence_ids
                if evidence_id in allowed_evidence_ids
            ]
            cells_payload.append(
                {
                    "competitor_id": cell.competitor_id,
                    "stance": cell.stance,
                    "summary": cell.summary,
                    "evidence_ids": grounded_evidence_ids,
                }
            )
        if not cells_payload:
            continue
        comparison_briefs.append(
            {
                "dimension": comparison.dimension,
                "cells": cells_payload,
            }
        )
    return comparison_briefs


def _build_fallback_report(
    *,
    template_id: str | None,
    target_sections: list[str],
    evidence_ids: list[str],
    analyst_summary: str,
    insight_briefs: list[dict[str, object]],
    evidence_briefs: list[dict[str, object]],
    risk_flags: list[str],
) -> dict[str, object]:
    sections: list[dict[str, object]] = []
    uncovered_sections: list[str] = []
    for section_id in target_sections:
        related_insights = _select_insights_for_section(
            section_id=section_id,
            insight_briefs=insight_briefs,
        )
        if related_insights:
            insight_refs = [
                item["insight_id"]
                for item in related_insights
                if isinstance(item.get("insight_id"), str)
            ]
        else:
            insight_refs = []

        evidence_refs = _select_evidence_ids_for_section(
            section_id=section_id,
            evidence_briefs=evidence_briefs,
            evidence_ids=evidence_ids,
        )
        for insight in related_insights:
            evidence_ids_raw = insight.get("evidence_ids")
            if not isinstance(evidence_ids_raw, list):
                continue
            for evidence_id in evidence_ids_raw:
                if isinstance(evidence_id, str) and evidence_id in evidence_ids:
                    evidence_refs.append(evidence_id)
        evidence_refs = _stable_unique([item for item in evidence_refs if item in evidence_ids])[:4]

        if related_insights:
            insight_lines = [
                f"- {item['finding']} (confidence: {item.get('confidence', 'medium')})"
                for item in related_insights
                if isinstance(item.get("finding"), str)
            ]
        else:
            insight_lines = [
                f"- {item['quote_preview']} [{item['competitor_id']}]"
                for item in evidence_briefs
                if item.get("evidence_id") in evidence_refs and item.get("quote_preview")
            ][:3]
        if not insight_lines:
            uncovered_sections.append(section_id)
            insight_lines = [
                "- No grounded evidence matched this section; keep it open for follow-up research."
            ]
        content_markdown = "\n".join(insight_lines)
        sections.append(
            {
                "section_id": section_id,
                "title": section_id.replace("_", " ").title(),
                "content_markdown": content_markdown,
                "evidence_refs": evidence_refs,
                "insight_refs": _stable_unique(insight_refs),
            }
        )

    if not sections:
        section_id = target_sections[0] if target_sections else "general"
        uncovered_sections.append(section_id)
        sections.append(
            {
                "section_id": section_id,
                "title": section_id.replace("_", " ").title(),
                "content_markdown": (
                    "Fallback writer generated a minimal section because no valid target sections were resolved "
                    "from request/recommended inputs."
                ),
                "evidence_refs": [],
                "insight_refs": [],
            }
        )

    summary = analyst_summary.strip() if analyst_summary.strip() else "Fallback writer summary from analyst context."
    return {
        "template_id": template_id or "default",
        "title": "RivalLens Competitive Battlecard",
        "executive_summary": summary,
        "sections": sections,
        "risk_callouts": _stable_unique(
            [
                *(risk_flags or ["writer_fallback_mode"]),
                *(f"uncovered_section:{section_id}" for section_id in uncovered_sections),
            ]
        ),
    }


def _render_report_markdown(
    report_content: dict[str, object],
    *,
    allowed_evidence_ids: set[str],
    response_language: str | None = None,
    evidence_briefs: list[dict[str, object]] | None = None,
) -> str:
    labels = (
        {
            "default_title": "RivalLens 报告",
            "executive_summary": "执行摘要",
            "section": "章节",
            "no_executive_summary": "暂无执行摘要。",
            "no_content": "暂无内容。",
            "evidence": "证据",
            "risk_callouts": "风险提示",
            "methodology": "数据来源与方法论",
            "methodology_generated_on": "生成日期(UTC)",
            "methodology_competitors": "覆盖竞品",
            "methodology_evidence_total": "证据总数",
            "methodology_authority_distribution": "来源等级分布",
            "methodology_source_type_distribution": "来源类型分布",
            "methodology_data_gaps": "数据缺口披露",
            "methodology_no_competitors": "未识别竞品",
            "methodology_gap_official_and_pricing": "官方来源和定价页均未覆盖（仅第三方资料）",
            "methodology_gap_official_only": "官方来源未覆盖（仅第三方资料）",
            "methodology_gap_pricing_only": "定价页未覆盖（定价可能未公开）",
            "methodology_no_data_gaps": "当前证据未发现明显来源缺口",
            "methodology_none": "无",
        }
        if response_language == "zh"
        else {
            "default_title": "RivalLens Report",
            "executive_summary": "Executive Summary",
            "section": "Section",
            "no_executive_summary": "No executive summary.",
            "no_content": "No content.",
            "evidence": "Evidence",
            "risk_callouts": "Risk Callouts",
            "methodology": "Data Sources and Methodology",
            "methodology_generated_on": "Generated on (UTC)",
            "methodology_competitors": "Covered competitors",
            "methodology_evidence_total": "Total evidence",
            "methodology_authority_distribution": "Source authority distribution",
            "methodology_source_type_distribution": "Source type distribution",
            "methodology_data_gaps": "Data gap disclosure",
            "methodology_no_competitors": "No identified competitors",
            "methodology_gap_official_and_pricing": (
                "official sources and pricing pages are both missing "
                "(third-party evidence only)"
            ),
            "methodology_gap_official_only": "official sources are missing (third-party evidence only)",
            "methodology_gap_pricing_only": "pricing pages are missing (pricing may not be public)",
            "methodology_no_data_gaps": "No obvious source gaps in current evidence",
            "methodology_none": "none",
        }
    )
    title_raw = report_content.get("title")
    title = title_raw.strip() if isinstance(title_raw, str) and title_raw.strip() else labels["default_title"]
    executive_summary_raw = report_content.get("executive_summary")
    executive_summary = (
        executive_summary_raw.strip()
        if isinstance(executive_summary_raw, str) and executive_summary_raw.strip()
        else labels["no_executive_summary"]
    )
    executive_summary = _sanitize_report_markdown_text(
        executive_summary,
        allowed_evidence_ids=allowed_evidence_ids,
    )
    markdown_lines = [
        f"# {title}",
        "",
        f"## {labels['executive_summary']}",
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
                else labels["section"]
            )
            if _is_duplicate_executive_summary_section(
                section_title=section_title,
                executive_summary_label=labels["executive_summary"],
            ):
                continue
            section_body_raw = section.get("content_markdown")
            section_body = (
                section_body_raw.strip()
                if isinstance(section_body_raw, str) and section_body_raw.strip()
                else labels["no_content"]
            )
            section_body = _sanitize_report_markdown_text(
                section_body,
                allowed_evidence_ids=allowed_evidence_ids,
            )
            markdown_lines.extend(
                [
                    f"## {section_title}",
                    section_body,
                ]
            )
            evidence_refs_raw = section.get("evidence_refs")
            if isinstance(evidence_refs_raw, list):
                evidence_refs = [
                    item
                    for item in evidence_refs_raw
                    if isinstance(item, str) and item in allowed_evidence_ids
                ]
            else:
                evidence_refs = []
            if evidence_refs:
                markdown_lines.append(
                    f"{labels['evidence']}: "
                    + ", ".join(f"[{evidence_id}]" for evidence_id in evidence_refs)
                )
            markdown_lines.append("")

    risk_callouts_raw = report_content.get("risk_callouts")
    if isinstance(risk_callouts_raw, list):
        risk_callouts = [item for item in risk_callouts_raw if isinstance(item, str)]
    else:
        risk_callouts = []
    if risk_callouts:
        markdown_lines.append(f"## {labels['risk_callouts']}")
        for item in risk_callouts:
            sanitized_item = _sanitize_report_markdown_text(
                item,
                allowed_evidence_ids=allowed_evidence_ids,
            )
            if sanitized_item:
                markdown_lines.append(f"- {sanitized_item}")
        markdown_lines.append("")

    methodology_lines = _build_methodology_section_lines(
        evidence_briefs=evidence_briefs or [],
        labels=labels,
    )
    markdown_lines.extend(
        [
            f"## {labels['methodology']}",
            *methodology_lines,
            "",
        ]
    )

    return "\n".join(markdown_lines).strip() + "\n"


@log_node("writer")
async def writer_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for writer node.")

    session_factory = get_session_factory()
    request = Write.model_validate(state.get("pending_tool_args", {}))
    step_id = make_id("step_")
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_START,
        step_id=step_id,
        payload={
            "agent_name": "writer",
            "template_id": request.template_id,
        },
    )
    report_id = f"report_{uuid4().hex[:12]}"
    evidence_rows, analyst_output = await _load_writer_inputs(
        session_factory=session_factory,
        run_id=run_id,
    )
    evidence_briefs = _build_evidence_briefs(evidence_rows)
    allowed_evidence_ids = {item["evidence_id"] for item in evidence_briefs}
    insight_briefs = _build_insight_briefs(
        analyst_output=analyst_output,
        allowed_evidence_ids=allowed_evidence_ids,
    )
    comparison_briefs = _build_comparison_briefs(
        analyst_output=analyst_output,
        allowed_evidence_ids=allowed_evidence_ids,
    )
    allowed_insight_ids = {
        item["insight_id"]
        for item in insight_briefs
        if isinstance(item.get("insight_id"), str)
    }
    execution_context = WriterExecutionContext.resolve(
        template_id=request.template_id,
        requested_sections=request.sections,
        analyst_output=analyst_output,
        allowed_evidence_ids=allowed_evidence_ids,
        allowed_insight_ids=allowed_insight_ids,
    )
    target_sections = execution_context.target_sections
    intake_draft = coerce_intake_draft_or_default(state)
    report_depth = _report_depth_from_state(state)
    analyst_summary = analyst_output.summary
    risk_flags = list(analyst_output.risk_flags)
    fallback_user_prompt = build_writer_fallback_user_prompt(
        template_id=request.template_id,
        requested_sections=target_sections,
        evidence_ids=sorted(allowed_evidence_ids),
        analyst_summary=analyst_summary,
    )
    harness_result = await complete_structured(
        model_slot="writer",
        system_prompt=WRITER_SYSTEM_PROMPT,
        user_prompt=build_writer_user_prompt(
            user_query=str(state.get("user_query", "")),
            template_id=request.template_id,
            target_sections=target_sections,
            requested_sections=request.sections or [],
            competitors=list(state.get("competitors", [])),
            evidence_briefs=evidence_briefs,
            allowed_evidence_ids=sorted(allowed_evidence_ids),
            analyst_summary=analyst_summary,
            analyst_insights=insight_briefs,
            analyst_comparisons=comparison_briefs,
            risk_flags=risk_flags,
            recommended_sections=analyst_output.recommended_sections,
            qa_reasons=request.qa_reasons,
            unsupported_numeric_claims=request.unsupported_numeric_claims,
            report_depth=report_depth,
            domain_hint=intake_draft.domain_hint,
            analysis_intent=intake_draft.analysis_intent,
            market_scope=intake_draft.market_scope,
            response_language=intake_draft.response_language,
            analysis_archetype=intake_draft.analysis_archetype,
        ),
        output_model=WriterReportOutput,
        parser=lambda content: WriterReportOutput.parse_llm_content(
            content,
            execution_context=execution_context,
        ),
        fallback_system_prompt=WRITER_SYSTEM_PROMPT,
        fallback_user_prompt=fallback_user_prompt,
        repair_user_prompt_builder=lambda errors: build_writer_repair_user_prompt(
            validation_errors=errors,
            template_id=request.template_id,
            target_sections=target_sections,
            evidence_ids=sorted(allowed_evidence_ids),
            analyst_summary=analyst_summary,
        ),
        log_event="writer.harness.finish",
    )
    llm_response = harness_result.llm_response
    writer_schema_error: str | None = None
    writer_mode: Literal["llm", "fallback"]
    if harness_result.value is not None:
        writer_mode = "llm"
        report_mode = (
            "primary"
            if harness_result.outcome in {"primary", "repaired"}
            else "llm_fallback"
        )
        report_content = harness_result.value.to_report_content()
        fallback_reason = llm_response.fallback_reason
    else:
        writer_mode = "fallback"
        report_mode = "deterministic_fallback"
        if llm_response.error is None:
            writer_schema_error = harness_result.schema_error or "writer_output_schema_invalid"
        fallback_reason = llm_response.error or writer_schema_error
        report_content = _build_fallback_report(
            template_id=request.template_id,
            target_sections=target_sections,
            evidence_ids=sorted(allowed_evidence_ids),
            analyst_summary=analyst_summary,
            insight_briefs=insight_briefs,
            evidence_briefs=evidence_briefs,
            risk_flags=risk_flags,
        )
    log.info(
        "writer.report_mode",
        report_mode=report_mode,
        writer_mode=writer_mode,
        harness_outcome=harness_result.outcome,
        target_sections=target_sections,
        fallback_reason=fallback_reason,
        writer_schema_error=writer_schema_error,
        section_count=len(report_content.get("sections", []))
        if isinstance(report_content.get("sections"), list)
        else 0,
        llm_fallback_used=llm_response.fallback_used,
    )
    markdown = _render_report_markdown(
        report_content,
        allowed_evidence_ids=allowed_evidence_ids,
        response_language=intake_draft.response_language,
        evidence_briefs=evidence_briefs,
    )
    llm_call_error = llm_response.error or writer_schema_error
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
                "report_depth": report_depth,
                "target_sections": target_sections,
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
            build_llm_call_record(
                step_id=step_id,
                response=llm_response,
                error=llm_call_error,
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
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={
            "agent_name": "writer",
            "status": "completed",
            "writer_mode": writer_mode,
            "section_count": section_count,
        },
    )

    return {
        "report_draft_done": True,
        "pending_tool_args": {},
        "pending_review_target_step_id": step_id,
        "writer_report_fallback_mode": writer_mode == "fallback",
        "status": "running",
    }
