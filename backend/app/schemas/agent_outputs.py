from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from core.defaults import DEFAULT_FOCUS_DIMENSIONS
from schemas.contracts import normalize_dimension_or_none, validate_dimension, validate_section_id, validate_template_id

ConfidenceLevel = Literal["high", "medium", "low"]
ComparisonStance = Literal["leader", "competitive", "laggard", "unknown"]
DEFAULT_WRITER_SECTIONS: tuple[str, ...] = DEFAULT_FOCUS_DIMENSIONS
MIN_WRITER_SECTION_CHARS = 60


def stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def resolve_writer_target_sections(
    *,
    requested_sections: list[str] | None,
    recommended_sections: list[str],
) -> list[str]:
    """Single source of truth for writer section targets across analyst → writer."""
    targets: list[str] = []
    if requested_sections:
        for section_id in requested_sections:
            try:
                targets.append(validate_section_id(section_id))
            except ValueError:
                continue
    if not targets:
        for section_id in recommended_sections:
            try:
                targets.append(validate_section_id(section_id))
            except ValueError:
                continue
    if not targets:
        targets = list(DEFAULT_WRITER_SECTIONS)
    return stable_unique(targets)


def _filter_valid_section_ids(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        raw_value = value.strip()
        try:
            canonical = validate_section_id(raw_value)
        except ValueError:
            continue
        # Analyst-recommended sections must already be canonical section IDs.
        # Free-form titles should fall back to insight dimensions.
        if canonical != raw_value:
            continue
        normalized.append(canonical)
    return stable_unique(normalized)


class AnalystInsight(BaseModel):
    dimension: str
    finding: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: ConfidenceLevel = "medium"

    @field_validator("dimension")
    @classmethod
    def _validate_dimension(cls, value: str) -> str:
        return validate_dimension(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> ConfidenceLevel:
        if isinstance(value, str) and value in {"high", "medium", "low"}:
            return value  # type: ignore[return-value]
        return "medium"


class ComparisonCell(BaseModel):
    competitor_id: str = Field(min_length=1)
    stance: ComparisonStance = "unknown"
    summary: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("stance", mode="before")
    @classmethod
    def _normalize_stance(cls, value: object) -> ComparisonStance:
        if isinstance(value, str) and value in {"leader", "competitive", "laggard", "unknown"}:
            return value  # type: ignore[return-value]
        return "unknown"

    @model_validator(mode="after")
    def _require_evidence_for_qualified_stance(self) -> Self:
        if self.stance != "unknown" and not self.evidence_ids:
            self.stance = "unknown"
        return self


class DimensionComparison(BaseModel):
    dimension: str
    cells: list[ComparisonCell] = Field(min_length=2)

    @field_validator("dimension")
    @classmethod
    def _validate_dimension(cls, value: str) -> str:
        return validate_dimension(value)


class AnalystOutput(BaseModel):
    """Canonical analyst artifact consumed by writer and QA."""

    summary: str = Field(min_length=1)
    insights: list[AnalystInsight] = Field(min_length=1)
    comparisons: list[DimensionComparison] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    recommended_sections: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _canonicalize_recommended_sections(self) -> Self:
        from_insights = stable_unique([insight.dimension for insight in self.insights])
        from_llm = _filter_valid_section_ids(self.recommended_sections)
        self.recommended_sections = from_llm or from_insights
        return self

    @classmethod
    def parse_llm_content(
        cls,
        content: dict[str, object],
        *,
        allowed_evidence_ids: set[str],
        allowed_dimensions: set[str],
        competitors: set[str] | None = None,
        dropped_dimensions: dict[str, int] | None = None,
    ) -> AnalystOutput:
        insights_raw = content.get("insights")
        filtered_insights: list[dict[str, object]] = []
        if isinstance(insights_raw, list):
            for item in insights_raw:
                if not isinstance(item, dict):
                    continue
                dimension_raw = item.get("dimension")
                finding_raw = item.get("finding")
                evidence_ids_raw = item.get("evidence_ids")
                dimension, drop_reason = normalize_dimension_or_none(
                    dimension_raw,
                    allowed=allowed_dimensions,
                )
                if drop_reason is not None and dropped_dimensions is not None:
                    dropped_dimensions[drop_reason] = dropped_dimensions.get(drop_reason, 0) + 1
                if (
                    dimension is None
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
                filtered_insights.append(
                    {
                        "dimension": dimension,
                        "finding": finding_raw.strip(),
                        "evidence_ids": evidence_ids,
                        "confidence": item.get("confidence", "medium"),
                    }
                )
        comparisons_raw = content.get("comparisons")
        filtered_comparisons: list[dict[str, object]] = []
        allowed_competitors = {item.strip() for item in competitors or set() if item.strip()}
        if isinstance(comparisons_raw, list):
            for item in comparisons_raw:
                if not isinstance(item, dict):
                    continue
                dimension, drop_reason = normalize_dimension_or_none(
                    item.get("dimension"),
                    allowed=allowed_dimensions,
                )
                if drop_reason is not None and dropped_dimensions is not None:
                    dropped_dimensions[drop_reason] = dropped_dimensions.get(drop_reason, 0) + 1
                cells_raw = item.get("cells")
                if dimension is None or not isinstance(cells_raw, list):
                    continue
                filtered_cells: list[dict[str, object]] = []
                seen_competitors: set[str] = set()
                for cell in cells_raw:
                    if not isinstance(cell, dict):
                        continue
                    competitor_raw = cell.get("competitor_id")
                    summary_raw = cell.get("summary")
                    evidence_ids_raw = cell.get("evidence_ids")
                    if not isinstance(competitor_raw, str):
                        continue
                    competitor_id = competitor_raw.strip()
                    if (
                        not competitor_id
                        or competitor_id in seen_competitors
                        or (allowed_competitors and competitor_id not in allowed_competitors)
                        or not isinstance(summary_raw, str)
                        or not summary_raw.strip()
                    ):
                        continue
                    evidence_ids = (
                        [
                            evidence_id
                            for evidence_id in evidence_ids_raw
                            if isinstance(evidence_id, str) and evidence_id in allowed_evidence_ids
                        ]
                        if isinstance(evidence_ids_raw, list)
                        else []
                    )
                    seen_competitors.add(competitor_id)
                    filtered_cells.append(
                        {
                            "competitor_id": competitor_id,
                            "stance": cell.get("stance", "unknown"),
                            "summary": summary_raw.strip(),
                            "evidence_ids": stable_unique(evidence_ids),
                        }
                    )
                if len(filtered_cells) >= 2:
                    filtered_comparisons.append(
                        {
                            "dimension": dimension,
                            "cells": filtered_cells,
                        }
                    )
        payload = {
            "summary": content.get("summary"),
            "insights": filtered_insights,
            "comparisons": filtered_comparisons,
            "risk_flags": content.get("risk_flags") if isinstance(content.get("risk_flags"), list) else [],
            "recommended_sections": content.get("recommended_sections")
            if isinstance(content.get("recommended_sections"), list)
            else [],
        }
        return cls.model_validate(payload)

    @classmethod
    def parse_persisted(cls, payload: object) -> AnalystOutput | None:
        if not isinstance(payload, dict):
            return None
        insights_raw = payload.get("insights")
        if not isinstance(insights_raw, list) or not insights_raw:
            return None
        try:
            return cls.model_validate(payload)
        except ValidationError:
            return None

    def to_persisted_dict(self) -> dict[str, object]:
        return self.model_dump(mode="python")

    @classmethod
    def build_fallback(
        cls,
        *,
        focus_dimensions: list[str],
        evidence_briefs: list[dict[str, object]],
    ) -> AnalystOutput:
        covered_dimensions = stable_unique(
            [
                item["dimension"]
                for item in evidence_briefs
                if isinstance(item.get("dimension"), str) and item["dimension"]
            ]
        )
        uncovered_dimensions = [
            dimension
            for dimension in focus_dimensions
            if dimension not in covered_dimensions
        ]
        risk_flags = stable_unique(
            [
                "analyst_fallback_mode",
                *(f"uncovered_dimension:{dimension}" for dimension in uncovered_dimensions),
            ]
        )
        insights: list[AnalystInsight] = []
        if evidence_briefs:
            grouped: dict[str, list[dict[str, object]]] = {}
            for brief in evidence_briefs:
                if not isinstance(brief, dict):
                    continue
                dimension_raw = brief.get("dimension")
                dimension = (
                    dimension_raw
                    if isinstance(dimension_raw, str) and dimension_raw
                    else "general"
                )
                grouped.setdefault(dimension, []).append(brief)
            target_dims = focus_dimensions or list(grouped.keys()) or ["general"]
            for dimension in target_dims:
                dim_briefs = grouped.get(dimension, [])
                for brief in dim_briefs[:2]:
                    quote_raw = brief.get("quote") or brief.get("sanitized_text") or ""
                    if not isinstance(quote_raw, str) or not quote_raw.strip():
                        continue
                    evidence_id_raw = brief.get("evidence_id")
                    evidence_id = (
                        evidence_id_raw if isinstance(evidence_id_raw, str) else "ev_missing"
                    )
                    competitor_raw = brief.get("competitor_id")
                    competitor_id = (
                        competitor_raw if isinstance(competitor_raw, str) else "unknown"
                    )
                    excerpt = quote_raw.strip()[:220]
                    insights.append(
                        AnalystInsight(
                            dimension=dimension,
                            finding=(
                                f"Evidence excerpt from {competitor_id}: {excerpt}"
                            ),
                            evidence_ids=[evidence_id],
                            confidence="low",
                        )
                    )
            summary = (
                f"Fallback analysis aggregated {len(evidence_briefs)} evidence snippets "
                f"into {len(insights)} dimension-scoped excerpts across "
                f"{len(target_dims)} dimensions."
            )
        else:
            summary = "Fallback analysis generated without evidence; analyst should re-run after research recovers."
            dimension = focus_dimensions[0] if focus_dimensions else "general"
            insights.append(
                AnalystInsight(
                    dimension=dimension,
                    finding="No evidence available for analyst pass.",
                    evidence_ids=["ev_missing"],
                    confidence="low",
                )
            )
        if not insights:
            dimension = focus_dimensions[0] if focus_dimensions else "general"
            insights.append(
                AnalystInsight(
                    dimension=dimension,
                    finding="No usable evidence excerpts for analyst fallback.",
                    evidence_ids=["ev_missing"],
                    confidence="low",
                )
            )
            summary = "Fallback analysis could not extract usable evidence excerpts."
        return cls(
            summary=summary,
            insights=insights,
            comparisons=[],
            risk_flags=risk_flags,
            recommended_sections=covered_dimensions or focus_dimensions or [dimension],
        )


class WriterSectionOutput(BaseModel):
    section_id: str
    title: str = Field(min_length=1)
    content_markdown: str = Field(min_length=MIN_WRITER_SECTION_CHARS)
    evidence_refs: list[str] = Field(min_length=1)
    insight_refs: list[str] = Field(default_factory=list)

    @field_validator("section_id")
    @classmethod
    def _validate_section_id(cls, value: str) -> str:
        return validate_section_id(value)


class WriterExecutionContext(BaseModel):
    """Resolved writer contract: section targets + grounding sets."""

    model_config = ConfigDict(frozen=True)

    template_id: str | None
    target_sections: list[str]
    allowed_evidence_ids: frozenset[str]
    allowed_insight_ids: frozenset[str]
    default_risk_callouts: tuple[str, ...] = Field(default_factory=tuple)

    @classmethod
    def resolve(
        cls,
        *,
        template_id: str | None,
        requested_sections: list[str] | None,
        analyst_output: AnalystOutput,
        allowed_evidence_ids: set[str],
        allowed_insight_ids: set[str],
        default_risk_callouts: list[str] | None = None,
    ) -> WriterExecutionContext:
        return cls(
            template_id=template_id,
            target_sections=resolve_writer_target_sections(
                requested_sections=requested_sections,
                recommended_sections=analyst_output.recommended_sections,
            ),
            allowed_evidence_ids=frozenset(allowed_evidence_ids),
            allowed_insight_ids=frozenset(allowed_insight_ids),
            default_risk_callouts=tuple(default_risk_callouts or analyst_output.risk_flags),
        )


class WriterReportOutput(BaseModel):
    template_id: str
    title: str = Field(min_length=1)
    executive_summary: str = Field(min_length=1)
    sections: list[WriterSectionOutput] = Field(min_length=1)
    risk_callouts: list[str] = Field(default_factory=list)

    @field_validator("template_id")
    @classmethod
    def _validate_template_id(cls, value: str) -> str:
        return validate_template_id(value)

    @model_validator(mode="after")
    def _validate_against_execution_context(self, info: ValidationInfo) -> Self:
        context = info.context if info.context else {}
        allowed_evidence_ids: set[str] = context.get("allowed_evidence_ids", set())
        allowed_insight_ids: set[str] = context.get("allowed_insight_ids", set())
        target_sections: list[str] = context.get("target_sections", [])
        expected_template_id: str | None = context.get("template_id")

        if expected_template_id is not None and self.template_id != expected_template_id:
            raise ValueError(
                f"template_id mismatch: expected {expected_template_id!r}, got {self.template_id!r}"
            )

        normalized_sections: list[WriterSectionOutput] = []
        for section in self.sections:
            evidence_refs = [
                evidence_id
                for evidence_id in section.evidence_refs
                if evidence_id in allowed_evidence_ids
            ]
            if not evidence_refs:
                continue
            insight_refs = [
                insight_id
                for insight_id in section.insight_refs
                if insight_id in allowed_insight_ids
            ]
            normalized_sections.append(
                section.model_copy(
                    update={
                        "evidence_refs": stable_unique(evidence_refs),
                        "insight_refs": stable_unique(insight_refs),
                    }
                )
            )
        if not normalized_sections:
            raise ValueError("No sections remain after evidence grounding.")

        if target_sections:
            present = {section.section_id for section in normalized_sections}
            missing = [section_id for section_id in target_sections if section_id not in present]
            fallback_evidence_id = next(iter(allowed_evidence_ids), None)
            for section_id in missing:
                if fallback_evidence_id is None:
                    continue
                normalized_sections.append(
                    WriterSectionOutput(
                        section_id=section_id,
                        title=section_id.replace("_", " ").title(),
                        content_markdown=(
                            f"当前证据不足以支撑 {section_id} 维度的结论。"
                            "已采集材料未覆盖该维度，以下引用仅供溯源，请勿过度推断。"
                        ),
                        evidence_refs=[fallback_evidence_id],
                        insight_refs=[],
                    )
                )
            still_missing = [
                section_id for section_id in target_sections if section_id not in {
                    section.section_id for section in normalized_sections
                }
            ]
            if still_missing:
                self.risk_callouts = stable_unique(
                    [
                        *self.risk_callouts,
                        *(f"uncovered_section:{section_id}" for section_id in still_missing),
                    ]
                )

        self.sections = normalized_sections
        return self

    @classmethod
    def parse_llm_content(
        cls,
        content: dict[str, object],
        *,
        execution_context: WriterExecutionContext,
    ) -> WriterReportOutput:
        template_id_raw = content.get("template_id")
        if execution_context.template_id is not None:
            template_id = execution_context.template_id
        elif isinstance(template_id_raw, str) and template_id_raw.strip():
            template_id = template_id_raw.strip()
        else:
            template_id = "default"

        payload = {
            **content,
            "template_id": template_id,
        }
        risk_callouts_raw = payload.get("risk_callouts")
        if not isinstance(risk_callouts_raw, list):
            payload["risk_callouts"] = list(execution_context.default_risk_callouts)
        return cls.model_validate(
            payload,
            context={
                "allowed_evidence_ids": set(execution_context.allowed_evidence_ids),
                "allowed_insight_ids": set(execution_context.allowed_insight_ids),
                "target_sections": execution_context.target_sections,
                "template_id": execution_context.template_id,
            },
        )

    def to_report_content(self) -> dict[str, object]:
        return self.model_dump(mode="python")


from schemas.agent_outputs_pipeline import (  # noqa: E402
    DiscoveryExtractOutput,
    ExtractStructuredOutput,
    IntakeTurnOutput,
    PlannerOutput,
    QASemanticOutput,
    ResearcherCompressionOutput,
    ResearcherDecisionOutput,
    SkillCuratorHarnessOutput,
    SupervisorToolCallOutput,
)

__all__ = [
    "AnalystOutput",
    "ComparisonCell",
    "ComparisonStance",
    "ConfidenceLevel",
    "DEFAULT_WRITER_SECTIONS",
    "DimensionComparison",
    "DiscoveryExtractOutput",
    "ExtractStructuredOutput",
    "IntakeTurnOutput",
    "MIN_WRITER_SECTION_CHARS",
    "PlannerOutput",
    "QASemanticOutput",
    "ResearcherCompressionOutput",
    "ResearcherDecisionOutput",
    "SkillCuratorHarnessOutput",
    "SupervisorToolCallOutput",
    "WriterExecutionContext",
    "WriterReportOutput",
    "resolve_writer_target_sections",
    "stable_unique",
]
