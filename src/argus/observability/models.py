"""Per-stage execution records (Bible §8: every processing stage exposes metrics)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, text
from sqlalchemy.dialects.postgresql import JSONB
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


class EvalRun(Base):
    """Evaluation harness result (Phase 8): retrieval or investigation-quality metrics
    captured at a point in time, stamped with the pipeline/strategy versions that
    produced them so regressions are attributable."""

    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_kind_time", "kind", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str]  # retrieval | investigation
    metrics: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    golden_version: Mapped[int | None]
    pipeline_version: Mapped[int] = mapped_column(server_default=text("1"))
    strategy: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
