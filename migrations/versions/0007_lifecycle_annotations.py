"""annotations table + evidence.review column (V2 Phase 2 lifecycle + human collaboration).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "investigation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("investigations.id"),
            nullable=False,
        ),
        sa.Column("target", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_annotations_investigation_id", "annotations", ["investigation_id"])

    # app-level values: approved | rejected | NULL (unreviewed) — no enum type
    op.add_column("evidence", sa.Column("review", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence", "review")
    op.drop_index("ix_annotations_investigation_id", table_name="annotations")
    op.drop_table("annotations")
