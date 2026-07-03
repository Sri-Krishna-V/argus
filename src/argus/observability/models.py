"""Per-stage execution records (Bible §8: every processing stage exposes metrics)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from argus.core.db import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (Index("ix_pipeline_runs_stage_time", "stage", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[uuid.UUID | None]
    stage: Mapped[str]
    pipeline_version: Mapped[int] = mapped_column(server_default=text("1"))
    status: Mapped[str]  # success | failure
    duration_ms: Mapped[int]
    attempt: Mapped[int] = mapped_column(server_default=text("1"))
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
