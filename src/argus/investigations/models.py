"""Investigation platform tables. An investigation's evidence and report are derived
and rebuilt on refresh; investigation_events is the append-only replay record
(trigger-guarded, migration 0004)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from argus.core.db import Base
from argus.knowledge.models import _now, _uuid_pk


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    question: Mapped[str]
    # created | running | complete | failed | archived
    status: Mapped[str] = mapped_column(server_default="created")
    confidence: Mapped[float | None]
    confidence_breakdown: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    plan: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    company_ids: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    version: Mapped[int] = mapped_column(server_default=text("1"))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    statement: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Evidence(Base):
    """Persisted CollectedEvidence: investigation ↔ chunk with stance. The chunk FK is
    the citation guarantee — evidence cannot reference a chunk that doesn't exist."""

    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("investigation_id", "chunk_id"),)

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    stance: Mapped[str]  # supporting | contradicting | unknown
    rationale: Mapped[str]
    query: Mapped[str]
    excerpt: Mapped[str]
    scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    strategy: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    version: Mapped[int] = mapped_column(server_default=text("1"))
    executive_summary: Mapped[str]
    key_findings: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    risks: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    follow_up_questions: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    narrative: Mapped[str]
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class InvestigationLink(Base):
    """Typed link between investigations (PRD §11)."""

    __tablename__ = "investigation_links"

    src_investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), primary_key=True
    )
    dst_investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), primary_key=True
    )
    link_type: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class InvestigationTask(Base):
    """One DAG node (PRD-V2 1.2). depends_on holds task UUIDs as strings; readiness
    is derived (all deps complete), never stored — it cannot drift. Execution rides
    the jobs outbox: job.document_id carries the investigation id, payload the task id."""

    __tablename__ = "investigation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    task_type: Mapped[str]  # collect_evidence | synthesize (Phase 1)
    objective: Mapped[str]  # why this task exists (PRD-V2: interpretable planning)
    specialist: Mapped[str | None]  # assigned in Phase 5 (specialist registry)
    depends_on: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(server_default="pending")
    inputs: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    outputs: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class InvestigationEvent(Base):
    """Append-only execution history: every prompt, retrieval param, model version,
    and chunk ID that produced this investigation (Bible §13)."""

    __tablename__ = "investigation_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    event_type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
