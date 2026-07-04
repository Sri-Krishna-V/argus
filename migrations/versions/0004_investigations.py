"""Investigation platform tables: investigations, hypotheses, evidence, reports,
investigation_links, investigation_events (append-only — reuses the events_append_only
trigger function from 0002).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: str | None = "0003"
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
        "investigations",
        _uuid_pk(),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="created"),
        sa.Column("confidence", sa.Float),
        sa.Column("confidence_breakdown", JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        # retrieval inputs recorded at run time — the replay record's queryable half
        sa.Column("plan", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("company_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        _created_at(),
    )

    op.create_table(
        "hypotheses",
        _uuid_pk(),
        sa.Column(
            "investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id"),
            nullable=False, index=True,
        ),
        sa.Column("statement", sa.Text, nullable=False),
        _created_at(),
    )

    op.create_table(
        "evidence",
        _uuid_pk(),
        sa.Column(
            "investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id"),
            nullable=False, index=True,
        ),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id"), nullable=False),
        sa.Column(
            "document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column("stance", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("excerpt", sa.Text, nullable=False),
        sa.Column("scores", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("strategy", sa.Text, nullable=False),
        _created_at(),
        sa.UniqueConstraint("investigation_id", "chunk_id"),
    )

    op.create_table(
        "reports",
        _uuid_pk(),
        sa.Column(
            "investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id"),
            nullable=False, index=True,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("executive_summary", sa.Text, nullable=False),
        sa.Column("key_findings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risks", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("follow_up_questions", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("narrative", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        _created_at(),
    )

    op.create_table(
        "investigation_links",
        sa.Column(
            "src_investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id"),
            primary_key=True,
        ),
        sa.Column(
            "dst_investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id"),
            primary_key=True,
        ),
        sa.Column("link_type", sa.Text, primary_key=True),  # relates_to, supersedes, ...
        _created_at(),
    )

    op.create_table(
        "investigation_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id"),
            nullable=False, index=True,
        ),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
    )
    # same append-only invariant as the events table (function created in 0002)
    op.execute(
        """
        CREATE TRIGGER investigation_events_append_only
        BEFORE UPDATE OR DELETE ON investigation_events
        FOR EACH ROW EXECUTE FUNCTION events_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER investigation_events_append_only ON investigation_events")
    for table in (
        "investigation_events", "investigation_links", "reports",
        "evidence", "hypotheses", "investigations",
    ):
        op.drop_table(table)
