from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.competitor_diff import CompetitorDiff


async def persist_diffs(*, session: AsyncSession, diffs: list[CompetitorDiff]) -> None:
    """Bulk-insert CompetitorDiff records within the provided session."""
    for diff in diffs:
        session.add(diff)
