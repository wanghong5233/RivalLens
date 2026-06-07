from __future__ import annotations

from copy import deepcopy
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge import RunKnowledgeRecord
from schemas.ids import make_id


class RunKnowledgePayload(TypedDict):
    schema_version: str
    features: list[dict[str, object]]
    pricings: list[dict[str, object]]
    personas: list[dict[str, object]]
    coverage: dict[str, object]


EMPTY_RUN_KNOWLEDGE: RunKnowledgePayload = {
    "schema_version": "schema_v0.2",
    "features": [],
    "pricings": [],
    "personas": [],
    "coverage": {},
}


def _copy_empty_knowledge() -> RunKnowledgePayload:
    return deepcopy(EMPTY_RUN_KNOWLEDGE)


async def persist_knowledge_for_step(
    *,
    session: AsyncSession,
    run_id: str,
    step_id: str,
    schema_version: str,
    features: list[dict[str, object]],
    pricings: list[dict[str, object]],
    personas: list[dict[str, object]],
    coverage: dict[str, object],
) -> RunKnowledgeRecord:
    record = RunKnowledgeRecord(
        knowledge_id=make_id("knowledge_"),
        run_id=run_id,
        step_id=step_id,
        schema_version=schema_version,
        features=features,
        pricings=pricings,
        personas=personas,
        coverage=coverage,
    )
    session.add(record)
    return record


async def load_knowledge_for_run(
    *,
    session: AsyncSession,
    run_id: str,
) -> RunKnowledgePayload:
    row = (
        await session.execute(
            select(RunKnowledgeRecord)
            .where(RunKnowledgeRecord.run_id == run_id)
            .order_by(RunKnowledgeRecord.sequence_id.desc())
            .limit(1)
        )
    ).scalars().first()
    if row is None:
        return _copy_empty_knowledge()
    return {
        "schema_version": row.schema_version,
        "features": list(row.features),
        "pricings": list(row.pricings),
        "personas": list(row.personas),
        "coverage": dict(row.coverage),
    }
