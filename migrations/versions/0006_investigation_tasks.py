"""investigation_tasks: DAG nodes (V2 Phase 1 task orchestration).

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigation_tasks",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "investigation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("investigations.id"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("objective", sa.String(), nullable=False),
        sa.Column("specialist", sa.String(), nullable=True),
        sa.Column("depends_on", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("inputs", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("outputs", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index(
        "ix_investigation_tasks_investigation_id", "investigation_tasks", ["investigation_id"]
    )
    op.create_index(
        "ix_investigation_tasks_inv_status", "investigation_tasks", ["investigation_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("investigation_tasks")
