from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.contracts import validate_dimension
from schemas.supervisor import FocusDimension
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry


class ToolError(RuntimeError):
    """Raised when a researcher tool call cannot be fulfilled."""


@dataclass(slots=True)
class ToolObservation:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any]


def _snapshot_observation(
    *,
    tool_name: str,
    industry_pack_id: str,
    competitor_id: str,
    dimension: FocusDimension,
) -> ToolObservation:
    normalized_dimension = validate_dimension(dimension)
    pack_registry = get_industry_pack_registry()
    try:
        pack = pack_registry.get(industry_pack_id)
    except IndustryPackNotFound as exc:
        raise ToolError(f"industry_pack={industry_pack_id} is not loaded.") from exc

    competitor = pack.competitors.get(competitor_id)
    if competitor is None:
        raise ToolError(
            f"competitor_id={competitor_id} not found in industry_pack={industry_pack_id}."
        )

    snippets = competitor.snapshots.get(normalized_dimension, [])
    if not snippets:
        raise ToolError(
            f"No snapshot snippets for competitor_id={competitor_id}, dimension={dimension}."
        )

    snippet_rows = [
        {
            "quote": item.quote,
            "sanitized_text": item.quote,
            "source_url": item.source_url,
            "source_title": item.source_title,
            "source_type": "local_note",
            "desensitized": item.desensitized,
            "metadata": {
                "pack_id": industry_pack_id,
                "dimension": dimension,
                "normalized_dimension": normalized_dimension,
                "source": "industry_pack_snapshot",
            },
        }
        for item in snippets
    ]

    return ToolObservation(
        tool=tool_name,
        args={
            "industry_pack_id": industry_pack_id,
            "competitor_id": competitor_id,
            "dimension": dimension,
        },
        result={
            "industry_pack_id": industry_pack_id,
            "competitor_id": competitor.id,
            "competitor_display_name": competitor.display_name,
            "dimension": dimension,
            "normalized_dimension": normalized_dimension,
            "snippets": snippet_rows,
        },
    )


def pack_lookup(
    *,
    industry_pack_id: str,
    competitor_id: str,
    dimension: FocusDimension,
) -> ToolObservation:
    return _snapshot_observation(
        tool_name="pack_lookup",
        industry_pack_id=industry_pack_id,
        competitor_id=competitor_id,
        dimension=dimension,
    )


def lookup_offline_snapshot(
    *,
    industry_pack_id: str,
    competitor_id: str,
    dimension: FocusDimension,
) -> ToolObservation:
    return _snapshot_observation(
        tool_name="lookup_offline_snapshot",
        industry_pack_id=industry_pack_id,
        competitor_id=competitor_id,
        dimension=dimension,
    )
