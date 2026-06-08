from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from schemas.business import Feature, Persona, Pricing
from schemas.contracts import validate_dimension
from schemas.ids import make_id

CoverageStatus = Literal["complete", "partial", "insufficient_data", "missing"]
KnowledgeCoverage = dict[str, dict[str, CoverageStatus]]
SchemaBucket = Literal["feature", "pricing", "persona"]

SCHEMA_VERSION = "schema_v0.2"


@dataclass(frozen=True)
class KnowledgeExtractionResult:
    schema_version: str
    features: list[dict[str, object]]
    pricings: list[dict[str, object]]
    personas: list[dict[str, object]]
    coverage: KnowledgeCoverage
    extraction_mode: Literal["comparison", "landscape_skipped"]
    missing_reasons: dict[str, list[str]]


@dataclass(frozen=True)
class _EvidenceBrief:
    evidence_id: str
    competitor_id: str
    dimension: str | None
    quote_preview: str
    source_title: str


def _safe_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_dimension(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return validate_dimension(value)
    except ValueError:
        return None


def _normalize_competitors(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _normalize_evidence_briefs(
    *,
    evidence_briefs: list[dict[str, object]],
    competitors: set[str],
) -> list[_EvidenceBrief]:
    normalized: list[_EvidenceBrief] = []
    for item in evidence_briefs:
        evidence_id = _safe_string(item.get("evidence_id"))
        competitor_id = _safe_string(item.get("competitor_id"))
        if not evidence_id or not competitor_id or competitor_id == "unknown":
            continue
        if competitors and competitor_id not in competitors:
            continue
        normalized.append(
            _EvidenceBrief(
                evidence_id=evidence_id,
                competitor_id=competitor_id,
                dimension=_normalize_dimension(item.get("dimension")),
                quote_preview=_safe_string(item.get("quote_preview")),
                source_title=_safe_string(item.get("source_title")),
            )
        )
    return normalized


def _schema_bucket_for_dimension(dimension: str | None) -> SchemaBucket:
    if dimension is None:
        return "feature"
    if "pricing" in dimension or "price" in dimension or "cost" in dimension:
        return "pricing"
    if (
        "feedback" in dimension
        or "persona" in dimension
        or "buyer" in dimension
        or "user" in dimension
    ):
        return "persona"
    return "feature"


def _feature_name(*, brief: _EvidenceBrief, index: int) -> str:
    if brief.source_title:
        return brief.source_title[:80]
    if brief.dimension:
        return f"{brief.dimension} signal {index}"
    return f"capability signal {index}"


def _pricing_model_hint(evidence: list[_EvidenceBrief]) -> str:
    if not evidence:
        return "unknown"
    joined = " ".join([item.quote_preview for item in evidence]).lower()
    if "seat" in joined:
        return "seat"
    if "usage" in joined or "token" in joined:
        return "usage"
    if "subscription" in joined or "monthly" in joined or "annual" in joined:
        return "subscription"
    return "unknown"


def _persona_role(competitor_id: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "_"
        for character in competitor_id
    ).strip("_")
    return f"{normalized or 'unknown'}_buyer"


def _coverage_for_counts(
    *,
    feature_count: int,
    pricing_count: int,
    persona_count: int,
) -> dict[str, CoverageStatus]:
    feature_status: CoverageStatus
    if feature_count >= 3:
        feature_status = "complete"
    elif feature_count > 0:
        feature_status = "partial"
    else:
        feature_status = "insufficient_data"
    pricing_status: CoverageStatus = "complete" if pricing_count > 0 else "insufficient_data"
    feedback_status: CoverageStatus = "partial" if persona_count > 0 else "insufficient_data"
    return {
        "feature": feature_status,
        "pricing": pricing_status,
        "feedback": feedback_status,
    }


def _empty_coverage(competitors: list[str]) -> KnowledgeCoverage:
    return {
        competitor_id: {
            "feature": "insufficient_data",
            "pricing": "insufficient_data",
            "feedback": "insufficient_data",
        }
        for competitor_id in competitors
    }


def extract_knowledge_schema(
    *,
    evidence_briefs: list[dict[str, object]],
    competitors: list[str],
    focus_dimensions: list[str],
    analysis_archetype: str,
) -> KnowledgeExtractionResult:
    del focus_dimensions
    ordered_competitors = _normalize_competitors(competitors)
    competitor_set = set(ordered_competitors)
    normalized_evidence = _normalize_evidence_briefs(
        evidence_briefs=evidence_briefs,
        competitors=competitor_set,
    )
    if not ordered_competitors:
        ordered_competitors = _normalize_competitors(
            [item.competitor_id for item in normalized_evidence]
        )
        competitor_set = set(ordered_competitors)
    if analysis_archetype == "landscape":
        return KnowledgeExtractionResult(
            schema_version=SCHEMA_VERSION,
            features=[],
            pricings=[],
            personas=[],
            coverage=_empty_coverage(ordered_competitors),
            extraction_mode="landscape_skipped",
            missing_reasons={
                competitor_id: ["landscape:competitor_schema_not_required"]
                for competitor_id in ordered_competitors
            },
        )

    feature_by_competitor: dict[str, list[_EvidenceBrief]] = {
        competitor_id: [] for competitor_id in ordered_competitors
    }
    pricing_by_competitor: dict[str, list[_EvidenceBrief]] = {
        competitor_id: [] for competitor_id in ordered_competitors
    }
    persona_by_competitor: dict[str, list[_EvidenceBrief]] = {
        competitor_id: [] for competitor_id in ordered_competitors
    }
    for brief in normalized_evidence:
        if competitor_set and brief.competitor_id not in competitor_set:
            continue
        bucket = _schema_bucket_for_dimension(brief.dimension)
        if bucket == "pricing":
            pricing_by_competitor.setdefault(brief.competitor_id, []).append(brief)
        elif bucket == "persona":
            persona_by_competitor.setdefault(brief.competitor_id, []).append(brief)
        else:
            feature_by_competitor.setdefault(brief.competitor_id, []).append(brief)

    features: list[dict[str, object]] = []
    for competitor_id in ordered_competitors:
        seen_names: set[str] = set()
        for index, brief in enumerate(feature_by_competitor.get(competitor_id, [])[:8], start=1):
            feature_name = _feature_name(brief=brief, index=index)
            if feature_name in seen_names:
                continue
            seen_names.add(feature_name)
            try:
                features.append(
                    Feature.model_validate(
                        {
                            "id": make_id("feat_"),
                            "competitor_id": competitor_id,
                            "name": feature_name,
                            "parent_id": None,
                            "description": brief.quote_preview[:240] if brief.quote_preview else None,
                            "maturity": "unknown",
                            "evidence_ids": [brief.evidence_id],
                        }
                    ).model_dump(mode="python")
                )
            except ValidationError:
                continue

    pricings: list[dict[str, object]] = []
    for competitor_id in ordered_competitors:
        pricing_evidence = pricing_by_competitor.get(competitor_id, [])
        if not pricing_evidence:
            continue
        evidence_ids = list({item.evidence_id for item in pricing_evidence[:4]})
        try:
            pricings.append(
                Pricing.model_validate(
                    {
                        "id": make_id("price_"),
                        "competitor_id": competitor_id,
                        "model": _pricing_model_hint(pricing_evidence),
                        "tiers": [],
                        "free_plan": None,
                        "enterprise_plan": None,
                        "evidence_ids": evidence_ids,
                    }
                ).model_dump(mode="python")
            )
        except ValidationError:
            continue

    personas: list[dict[str, object]] = []
    persona_count_by_competitor: dict[str, int] = {competitor_id: 0 for competitor_id in ordered_competitors}
    for competitor_id in ordered_competitors:
        persona_evidence = persona_by_competitor.get(competitor_id, [])
        if not persona_evidence:
            continue
        first = persona_evidence[0]
        pain_point = first.quote_preview[:160] if first.quote_preview else ""
        try:
            personas.append(
                Persona.model_validate(
                    {
                        "id": make_id("persona_"),
                        "name": f"{competitor_id} buyer persona",
                        "role": _persona_role(competitor_id),
                        "pain_points": [pain_point] if pain_point else ["Buyer pain points need more evidence"],
                        "jobs_to_be_done": [],
                        "evidence_ids": [first.evidence_id],
                    }
                ).model_dump(mode="python")
            )
            persona_count_by_competitor[competitor_id] += 1
        except ValidationError:
            continue

    coverage: KnowledgeCoverage = {}
    missing_reasons: dict[str, list[str]] = {}
    for competitor_id in ordered_competitors:
        feature_count = sum(
            1
            for item in features
            if isinstance(item.get("competitor_id"), str) and item["competitor_id"] == competitor_id
        )
        pricing_count = sum(
            1
            for item in pricings
            if isinstance(item.get("competitor_id"), str) and item["competitor_id"] == competitor_id
        )
        persona_count = persona_count_by_competitor.get(competitor_id, 0)
        coverage[competitor_id] = _coverage_for_counts(
            feature_count=feature_count,
            pricing_count=pricing_count,
            persona_count=persona_count,
        )
        reasons: list[str] = []
        if feature_count == 0:
            reasons.append("feature:no_grounded_evidence")
        elif feature_count < 3:
            reasons.append("feature:coverage_partial")
        if pricing_count == 0:
            reasons.append("pricing:no_grounded_evidence")
        if persona_count == 0:
            reasons.append("persona:no_grounded_evidence")
        if reasons:
            missing_reasons[competitor_id] = reasons

    return KnowledgeExtractionResult(
        schema_version=SCHEMA_VERSION,
        features=features,
        pricings=pricings,
        personas=personas,
        coverage=coverage,
        extraction_mode="comparison",
        missing_reasons=missing_reasons,
    )


__all__ = [
    "KnowledgeCoverage",
    "KnowledgeExtractionResult",
    "extract_knowledge_schema",
]
