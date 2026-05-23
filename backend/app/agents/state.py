from __future__ import annotations

from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schemas.supervisor import SupervisorDecision


class AgentState(TypedDict, total=False):
    run_id: str
    user_query: str
    industry_pack: str
    competitors: list[str]
    decisions: list[SupervisorDecision]
    status: str
    session_factory: async_sessionmaker[AsyncSession]
