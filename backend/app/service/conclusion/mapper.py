from __future__ import annotations

from typing import TypedDict

from service.llm import WRITER_ALLOWED_SECTION_IDS


ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_SECTIONS = set(WRITER_ALLOWED_SECTION_IDS)


class MappedConclusion(TypedDict):
    section: str
    claim: str
    confidence: str
    evidence_ids: list[str]
    competitor_ids: list[str]
    risk_flags: list[str]


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _extract_competitor_id(lookup_item: object) -> str | None:
    if isinstance(lookup_item, dict):
        direct_competitor_id = lookup_item.get("competitor_id")
        if isinstance(direct_competitor_id, str) and direct_competitor_id.strip():
            return direct_competitor_id.strip()
        span = lookup_item.get("span")
        if isinstance(span, dict):
            nested_competitor_id = span.get("competitor_id")
            if isinstance(nested_competitor_id, str) and nested_competitor_id.strip():
                return nested_competitor_id.strip()

    span = getattr(lookup_item, "span", None)
    if isinstance(span, dict):
        competitor_id = span.get("competitor_id")
        if isinstance(competitor_id, str) and competitor_id.strip():
            return competitor_id.strip()
    return None


def _risk_flags_for_dimension(dimension: str, risk_flags: list[str]) -> list[str]:
    prefix = f"{dimension}_"
    return [item for item in risk_flags if item.startswith(prefix)]


def insights_to_conclusions(
    *,
    run_id: str,
    step_id: str,
    insights: list[dict[str, object]],
    evidence_lookup: dict[str, object],
    risk_flags: list[str],
) -> list[MappedConclusion]:
    del run_id, step_id
    mapped: list[MappedConclusion] = []
    for insight in insights:
        dimension_raw = insight.get("dimension")
        claim_raw = insight.get("finding")
        confidence_raw = insight.get("confidence")
        evidence_ids_raw = insight.get("evidence_ids")

        if (
            not isinstance(dimension_raw, str)
            or dimension_raw not in ALLOWED_SECTIONS
            or not isinstance(claim_raw, str)
            or not claim_raw.strip()
            or not isinstance(evidence_ids_raw, list)
        ):
            continue

        evidence_ids = [
            item
            for item in evidence_ids_raw
            if isinstance(item, str) and item in evidence_lookup
        ]
        evidence_ids = _stable_unique(evidence_ids)
        if not evidence_ids:
            continue

        confidence = (
            confidence_raw
            if isinstance(confidence_raw, str) and confidence_raw in ALLOWED_CONFIDENCE
            else "medium"
        )
        competitor_ids = _stable_unique(
            [
                competitor_id
                for competitor_id in (
                    _extract_competitor_id(evidence_lookup[evidence_id])
                    for evidence_id in evidence_ids
                )
                if competitor_id is not None
            ]
        )

        mapped.append(
            {
                "section": dimension_raw,
                "claim": claim_raw.strip(),
                "confidence": confidence,
                "evidence_ids": evidence_ids,
                "competitor_ids": competitor_ids,
                "risk_flags": _risk_flags_for_dimension(dimension_raw, risk_flags),
            }
        )
    return mapped
