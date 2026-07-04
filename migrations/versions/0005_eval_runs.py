"""eval_runs: point-in-time retrieval/investigation quality metrics (Phase 8).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        _uuid_pk(),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("metrics", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("golden_version", sa.Integer),
        sa.Column("pipeline_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("strategy", sa.Text, nullable=False),
        _created_at(),
    )
    op.create_index("ix_eval_runs_kind_time", "eval_runs", ["kind", "created_at"])


def downgrade() -> None:
    op.drop_table("eval_runs")
