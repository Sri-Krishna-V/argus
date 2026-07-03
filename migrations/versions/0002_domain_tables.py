"""Domain tables: documents, companies, chunks, mentions, graph, events, jobs, pipeline_runs.

Invariants enforced here at the schema level (docs/DOMAIN_MODEL.md):
- documents content columns are immutable (trigger)
- events is append-only (trigger)
- graph edges require source-document provenance (NOT NULL FK)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384  # keep in sync with argus.knowledge.models.EMBEDDING_DIM


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
        "documents",
        _uuid_pk(),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_native_id", sa.Text, nullable=False),
        sa.Column("checksum", sa.Text, nullable=False, index=True),
        sa.Column("raw_path", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("publisher", sa.Text),
        sa.Column("url", sa.Text),
        sa.Column("doc_type", sa.Text, nullable=False),
        sa.Column("language", sa.Text, nullable=False, server_default="en"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="ingested"),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("source", "source_native_id"),
    )

    op.create_table(
        "companies",
        _uuid_pk(),
        sa.Column("name", sa.Text, nullable=False, index=True),
        sa.Column("cik", sa.Text, unique=True),
        sa.Column("tickers", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("aliases", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("sector", sa.Text),
        sa.Column("industry", sa.Text),
        _created_at(),
    )

    op.create_table(
        "document_companies",
        sa.Column(
            "document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), primary_key=True
        ),
        sa.Column(
            "company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), primary_key=True
        ),
        sa.Column("resolution_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        _created_at(),
    )

    op.create_table(
        "chunks",
        _uuid_pk(),
        sa.Column(
            "document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"),
            nullable=False, index=True,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("embedding_model", sa.Text),
        sa.Column("pipeline_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "tsv", TSVECTOR,
            sa.Computed("to_tsvector('english', text)", persisted=True),
        ),
        _created_at(),
        sa.UniqueConstraint("document_id", "position", "pipeline_version"),
    )

    op.create_table(
        "entity_mentions",
        _uuid_pk(),
        sa.Column(
            "document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"),
            nullable=False, index=True,
        ),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id")),
        sa.Column("mention_text", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False, server_default="company"),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("resolved_company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id")),
        sa.Column("resolution_version", sa.Integer),
        sa.Column("pipeline_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        _created_at(),
    )

    op.create_table(
        "graph_nodes",
        _uuid_pk(),
        sa.Column("node_type", sa.Text, nullable=False),
        sa.Column("canonical_key", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id")),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
        sa.UniqueConstraint("node_type", "canonical_key"),
    )

    op.create_table(
        "graph_edges",
        _uuid_pk(),
        sa.Column(
            "src_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "dst_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_nodes.id"),
            nullable=False, index=True,
        ),
        sa.Column("edge_type", sa.Text, nullable=False),
        sa.Column(
            "source_document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column("pipeline_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        _created_at(),
        sa.UniqueConstraint("src_node_id", "dst_node_id", "edge_type", "source_document_id"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("event_type", sa.Text, nullable=False, index=True),
        sa.Column("aggregate_type", sa.Text, nullable=False, server_default="document"),
        sa.Column("aggregate_id", UUID(as_uuid=True)),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("event_id", sa.BigInteger, sa.ForeignKey("events.id")),
        sa.Column("job_type", sa.Text, nullable=False),
        sa.Column("document_id", UUID(as_uuid=True)),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default=sa.text("3")),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        _created_at(),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "run_after"])

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True)),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("pipeline_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.Text),
        _created_at(),
    )
    op.create_index("ix_pipeline_runs_stage_time", "pipeline_runs", ["stage", "created_at"])

    # Invariant 1: document content is immutable; only workflow columns may change.
    op.execute(
        """
        CREATE FUNCTION documents_immutable_guard() RETURNS trigger AS $$
        BEGIN
            IF (NEW.id, NEW.source, NEW.source_native_id, NEW.checksum, NEW.raw_path,
                NEW.title, NEW.publisher, NEW.url, NEW.doc_type, NEW.language,
                NEW.published_at, NEW.ingested_at, NEW.extra)
               IS DISTINCT FROM
               (OLD.id, OLD.source, OLD.source_native_id, OLD.checksum, OLD.raw_path,
                OLD.title, OLD.publisher, OLD.url, OLD.doc_type, OLD.language,
                OLD.published_at, OLD.ingested_at, OLD.extra)
            THEN
                RAISE EXCEPTION 'documents are immutable: only status/version may change';
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql;

        CREATE TRIGGER documents_immutable BEFORE UPDATE ON documents
        FOR EACH ROW EXECUTE FUNCTION documents_immutable_guard();
        """
    )

    # Invariant 2: the event log is append-only.
    op.execute(
        """
        CREATE FUNCTION events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'events are append-only';
        END $$ LANGUAGE plpgsql;

        CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION events_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER events_append_only ON events")
    op.execute("DROP FUNCTION events_append_only()")
    op.execute("DROP TRIGGER documents_immutable ON documents")
    op.execute("DROP FUNCTION documents_immutable_guard()")
    for table in (
        "pipeline_runs", "jobs", "events", "graph_edges", "graph_nodes",
        "entity_mentions", "chunks", "document_companies", "companies", "documents",
    ):
        op.drop_table(table)
