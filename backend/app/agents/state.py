from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schemas.supervisor import SupervisorDecision


class AgentState(TypedDict, total=False):
    run_id: str
    user_query: str
    industry_pack: str
    competitors: list[str]
    current_iteration: int
    pending_tool_args: dict[str, object]
    next_action: Literal["researcher", "analyst", "writer", "finalize"]
    last_completed_node: Literal["researcher", "analyst", "writer"] | None
    researched_competitors: list[str]
    analysis_done: bool
    report_draft_done: bool
    decisions: list[SupervisorDecision]
    status: str
    session_factory: async_sessionmaker[AsyncSession]
