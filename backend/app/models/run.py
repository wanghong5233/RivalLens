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
