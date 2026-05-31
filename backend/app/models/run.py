from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    domain_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    competitors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # Phase 1b: Agent-native intake snapshot. Persisted at intake.complete so the
    # FE can render "what you asked for" on the live run page even after restart.
    # `phase` is derived (status + intake_draft + plan_tree), so we deliberately
    # do NOT store a phase column — YAGNI and avoids drift with the graph state.
    intake_draft: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    # Phase 2 placeholder (planner output); ships in the same migration to avoid
    # a second DDL round-trip when the planner lands.
    plan_tree: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    # Phase 4 follow-up inbox. List of `FollowUpEntry`-shaped dicts; pending
    # entries (consumed_at is null) are read at supervisor entry and marked
    # consumed after the iteration's decision is persisted. Stored on `runs`
    # (not a separate table) because it's bounded per run + only queried by
    # run_id; a dedicated table would add a join without buying anything.
    follow_ups: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
