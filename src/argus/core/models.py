"""Eventing tables (ADR-0003): events is the append-only source of truth,
jobs is the disposable outbox derived from it."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from argus.core.db import Base

_now = text("now()")


class Event(Base):
    """Append-only (UPDATE/DELETE rejected by trigger, migration 0002).
    The bigint identity id doubles as the subscriber cursor."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_type: Mapped[str] = mapped_column(index=True)  # document.ingested, ...
    aggregate_type: Mapped[str] = mapped_column(server_default="document")
    aggregate_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Job(Base):
    """Outbox work item, claimed with FOR UPDATE SKIP LOCKED.
    status: pending → running → completed | failed(retry) | dead."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("events.id"))
    job_type: Mapped[str]  # pipeline stage or connector name
    document_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(server_default="pending")
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(server_default=text("3"))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
