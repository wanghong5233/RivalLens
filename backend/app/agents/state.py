from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schemas.supervisor import SupervisorDecision


def _last_write_wins(_: object, new: object) -> object:
    return new


class AgentState(TypedDict, total=False):
    run_id: str
    user_query: str
    domain_hint: str | None
    reference_urls: list[str]
    competitors: Annotated[list[str], operator.add]
    discovered_competitors: Annotated[list[str], operator.add]
    current_iteration: int
    pending_tool_args: Annotated[dict[str, object], _last_write_wins]
    next_action: Literal["discovery", "researcher", "analyst", "writer", "finalize"]
    last_completed_node: Annotated[
        Literal["researcher", "analyst", "writer"] | None,
        _last_write_wins,
    ]
    qa_outcome: Literal["approved", "rejected", "force_degraded"] | None
    qa_reject_to: Literal["researcher", "analyst", "writer", "supervisor"] | None
    qa_rejection_count: int
    pending_review_target_step_id: str | None
    qa_reasons: list[str]
    researched_competitors: Annotated[list[str], operator.add]
    analysis_done: bool
    report_draft_done: bool
    decisions: list[SupervisorDecision]
    status: Annotated[str, _last_write_wins]
    session_factory: async_sessionmaker[AsyncSession]
