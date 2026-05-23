from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.supervisor import FocusDimension
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry


class ToolError(RuntimeError):
    """Raised when a researcher tool call cannot be fulfilled."""


@dataclass(slots=True)
class ToolObservation:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any]


def pack_lookup(
    *,
    industry_pack_id: str,
    competitor_id: str,
    dimension: FocusDimension,
) -> ToolObservation:
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

    snippets = competitor.snapshots.get(dimension, [])
    if not snippets:
        raise ToolError(
            f"No snapshot snippets for competitor_id={competitor_id}, dimension={dimension}."
        )

    snippet_rows = [
        {
            "quote": item.quote,
            "source_url": item.source_url,
            "source_title": item.source_title,
            "desensitized": item.desensitized,
        }
        for item in snippets
    ]

    return ToolObservation(
        tool="pack_lookup",
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
            "snippets": snippet_rows,
        },
    )
