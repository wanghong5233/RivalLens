from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from models.artifact import Artifact
from models.evidence import EvidenceRecord
from models.step import Step
from schemas.ids import make_id
from schemas.supervisor import ConductResearch, FocusDimension
from service.industry_pack.models import CompetitorSnapshot, IndustryPack
from service.industry_pack.registry import IndustryPackNotFound, get_industry_pack_registry


def _require_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is None:
        raise RuntimeError("AgentState.session_factory is required for researcher node.")
    return session_factory


def _require_industry_pack_id(state: AgentState) -> str:
    industry_pack_id = state.get("industry_pack")
    if industry_pack_id is None:
        raise RuntimeError("AgentState.industry_pack is required for researcher node.")
    return industry_pack_id


def _resolve_competitor_snapshot(
    *,
    pack: IndustryPack,
    competitor_id: str,
) -> CompetitorSnapshot:
    competitor = pack.competitors.get(competitor_id)
    if competitor is None:
        raise RuntimeError(
            f"competitor_id={competitor_id} not found in industry_pack={pack.id}."
        )
    return competitor


def _resolve_focus_dimensions(
    *,
    request: ConductResearch,
    pack: IndustryPack,
) -> list[FocusDimension]:
    focus_dimensions = list(request.focus_dimensions or pack.default_focus_dimensions)
    if not focus_dimensions:
        raise RuntimeError(
            f"No focus_dimensions available for industry_pack={pack.id} and competitor_id={request.competitor_id}."
        )
    return focus_dimensions


def _build_evidence_rows(
    *,
    run_id: str,
    step_id: str,
    collected_at: datetime,
    pack_id: str,
    competitor: CompetitorSnapshot,
    focus_dimensions: list[FocusDimension],
) -> tuple[list[EvidenceRecord], list[str]]:
    evidence_rows: list[EvidenceRecord] = []
    evidence_ids: list[str] = []
    for dimension in focus_dimensions:
        snippets = competitor.snapshots.get(dimension, [])
        if not snippets:
            raise RuntimeError(
                f"No snapshot snippet for dimension={dimension} in competitor={competitor.id}."
            )
        for snippet in snippets:
            evidence_id = make_id("ev_")
            evidence_ids.append(evidence_id)
            evidence_rows.append(
                EvidenceRecord(
                    id=evidence_id,
                    run_id=run_id,
                    source_type="industry_pack_snapshot",
                    source_url=snippet.source_url,
                    source_title=snippet.source_title,
                    quote=snippet.quote,
                    sanitized_text=snippet.quote,
                    span={
                        "dimension": dimension,
                        "competitor_id": competitor.id,
                        "pack_id": pack_id,
                    },
                    collected_by=step_id,
                    collected_at=collected_at,
                    desensitized=snippet.desensitized,
                )
            )
    return evidence_rows, evidence_ids


async def researcher_node(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    if run_id is None:
        raise RuntimeError("AgentState.run_id is required for researcher node.")

    industry_pack_id = _require_industry_pack_id(state)
    session_factory = _require_session_factory(state)
    request = ConductResearch.model_validate(state.get("pending_tool_args", {}))
    pack_registry = get_industry_pack_registry()
    try:
        pack = pack_registry.get(industry_pack_id)
    except IndustryPackNotFound as exc:
        raise RuntimeError(f"industry_pack={industry_pack_id} is not loaded.") from exc

    competitor = _resolve_competitor_snapshot(pack=pack, competitor_id=request.competitor_id)
    focus_dimensions = _resolve_focus_dimensions(request=request, pack=pack)
    step_id = make_id("step_")
    collected_at = datetime.now(timezone.utc)
    evidence_rows, evidence_ids = _build_evidence_rows(
        run_id=run_id,
        step_id=step_id,
        collected_at=collected_at,
        pack_id=pack.id,
        competitor=competitor,
        focus_dimensions=focus_dimensions,
    )
    step_payload = {
        **request.model_dump(),
        "pack_id": pack.id,
        "focus_dimensions": focus_dimensions,
        "evidence_ids": evidence_ids,
    }

    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="researcher",
            status="running",
            retry_count=0,
            payload=step_payload,
        )
        session.add(step)
        await session.flush()
        for evidence_row in evidence_rows:
            session.add(evidence_row)
        session.add(
            Artifact(
                artifact_id=make_id("artifact_"),
                step_id=step_id,
                kind="research_fragment",
                uri=f"memory://research/{run_id}/{competitor.id}",
                sha256=None,
                size_bytes=None,
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()

    researched_competitors = list(state.get("researched_competitors", []))
    if request.competitor_id not in researched_competitors:
        researched_competitors.append(request.competitor_id)

    return {
        **state,
        "researched_competitors": researched_competitors,
        "pending_tool_args": {},
        "last_completed_node": "researcher",
        "status": "running",
    }
