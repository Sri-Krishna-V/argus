"""Hybrid retrieval (Bible §16): lexical FTS + semantic pgvector fused with
reciprocal rank fusion, plus metadata/entity/temporal filters. Every result carries
per-signal ranks and the strategy version — the reproducibility record."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from argus.dataplatform.embeddings import get_provider
from argus.knowledge.models import Chunk, Document, DocumentCompany

STRATEGY_VERSION = "hybrid-rrf/v1"
RRF_K = 60  # standard damping constant
POOL_FACTOR = 3  # each signal contributes k * POOL_FACTOR candidates


@dataclass
class SearchFilters:
    company_id: uuid.UUID | None = None
    doc_types: list[str] | None = None
    sources: list[str] | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None


@dataclass
class RetrievalResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    title: str | None
    url: str | None
    source: str
    doc_type: str
    published_at: datetime | None
    scores: dict = field(default_factory=dict)
    strategy: str = STRATEGY_VERSION


def _base_query(filters: SearchFilters):
    q = select(Chunk.id).join(Document, Document.id == Chunk.document_id)
    if filters.company_id:
        q = q.join(
            DocumentCompany,
            (DocumentCompany.document_id == Document.id)
            & (DocumentCompany.company_id == filters.company_id),
        )
    if filters.doc_types:
        q = q.where(Document.doc_type.in_(filters.doc_types))
    if filters.sources:
        q = q.where(Document.source.in_(filters.sources))
    if filters.published_after:
        q = q.where(Document.published_at >= filters.published_after)
    if filters.published_before:
        q = q.where(Document.published_at <= filters.published_before)
    return q


def search(
    session: Session,
    query: str,
    filters: SearchFilters | None = None,
    k: int = 10,
) -> list[RetrievalResult]:
    if not query.strip() or k <= 0:  # ponytail: nothing to rank; avoid empty/zero-limit edge cases
        return []
    filters = filters or SearchFilters()
    pool = k * POOL_FACTOR

    semantic_ids = session.scalars(
        _base_query(filters)
        .where(Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(get_provider().embed([query])[0]))
        .limit(pool)
    ).all()

    tsquery = func.plainto_tsquery("english", query)
    lexical_ids = session.scalars(
        _base_query(filters)
        .where(Chunk.tsv.op("@@")(tsquery))
        .order_by(func.ts_rank(Chunk.tsv, tsquery).desc())
        .limit(pool)
    ).all()

    # reciprocal rank fusion across both signals
    ranks: dict[uuid.UUID, dict] = {}
    for signal, ids in (("semantic", semantic_ids), ("lexical", lexical_ids)):
        for rank, chunk_id in enumerate(ids, start=1):
            entry = ranks.setdefault(chunk_id, {"rrf": 0.0})
            entry[f"{signal}_rank"] = rank
            entry["rrf"] += 1.0 / (RRF_K + rank)
    top = sorted(ranks.items(), key=lambda kv: kv[1]["rrf"], reverse=True)[:k]

    rows = {
        chunk.id: (chunk, doc)
        for chunk, doc in session.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_([cid for cid, _ in top]))
        ).all()
    }
    return [
        RetrievalResult(
            chunk_id=chunk.id,
            document_id=doc.id,
            text=chunk.text,
            title=doc.title,
            url=doc.url,
            source=doc.source,
            doc_type=doc.doc_type,
            published_at=doc.published_at,
            scores=scores,
        )
        for cid, scores in top
        for chunk, doc in [rows[cid]]
    ]
