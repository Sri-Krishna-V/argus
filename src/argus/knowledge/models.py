"""Knowledge-layer tables. Invariants documented in docs/DOMAIN_MODEL.md."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from argus.core.db import Base

# all-MiniLM-L6-v2; changing models means a new pipeline_version and re-embed
EMBEDDING_DIM = 384

_uuid_pk = {"primary_key": True, "server_default": text("gen_random_uuid()")}
_now = text("now()")


class Document(Base):
    """Immutable source of truth. Content columns are trigger-guarded (migration 0002);
    only status/version advance."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source", "source_native_id"),)

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    source: Mapped[str]  # connector name: sec_edgar, rss, company_profiles
    source_native_id: Mapped[str]  # accession number, feed entry id, ...
    checksum: Mapped[str] = mapped_column(index=True)  # sha256 of raw bytes
    raw_path: Mapped[str]  # content-addressed path under the raw store
    title: Mapped[str | None]
    publisher: Mapped[str | None]
    url: Mapped[str | None]
    doc_type: Mapped[str]  # filing, news, transcript, profile
    language: Mapped[str] = mapped_column(server_default="en")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    status: Mapped[str] = mapped_column(server_default="ingested")
    version: Mapped[int] = mapped_column(server_default=text("1"))
    extra: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class Company(Base):
    """Canonical entity. One row per CIK; the entity-resolution target."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    name: Mapped[str] = mapped_column(index=True)
    cik: Mapped[str | None] = mapped_column(unique=True)
    tickers: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    sector: Mapped[str | None]
    industry: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class DocumentCompany(Base):
    """Resolved document ↔ company link, stamped with the resolver version."""

    __tablename__ = "document_companies"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), primary_key=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    resolution_version: Mapped[int] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Chunk(Base):
    """Derived, disposable, re-derivable. tsv column is DB-generated (migration 0002)."""

    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "position", "pipeline_version"),)

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    position: Mapped[int]
    text: Mapped[str]
    char_start: Mapped[int]
    char_end: Mapped[int]
    token_count: Mapped[int]
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None]
    pipeline_version: Mapped[int] = mapped_column(server_default=text("1"))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class EntityMention(Base):
    """An extracted occurrence of an entity in a document; resolution links it to the
    canonical company (resolved_company_id stays NULL when unresolved — never a guess)."""

    __tablename__ = "entity_mentions"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id"))
    mention_text: Mapped[str]
    entity_type: Mapped[str] = mapped_column(server_default="company")
    char_start: Mapped[int]
    char_end: Mapped[int]
    resolved_company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    resolution_version: Mapped[int | None]
    pipeline_version: Mapped[int] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("node_type", "canonical_key"),)

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    node_type: Mapped[str]  # company, sector, industry, region, event
    canonical_key: Mapped[str]  # e.g. company:<uuid>, sector:Technology
    label: Mapped[str]
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    extra: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class GraphEdge(Base):
    """Relationships are intelligence (Bible §18). source_document_id is NOT NULL:
    an edge without provenance cannot exist."""

    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint("src_node_id", "dst_node_id", "edge_type", "source_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    src_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    dst_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    edge_type: Mapped[str]  # mentioned_in, member_of_sector, ...
    source_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    pipeline_version: Mapped[int] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
