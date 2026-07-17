"""Hybrid retrieval (Bible §16): lexical FTS + semantic pgvector + graph traversal +
timeline recency fused with reciprocal rank fusion, plus metadata/entity/temporal
filters. Every result carries per-signal ranks and the strategy version — the
reproducibility record."""

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from argus.dataplatform.embeddings import get_provider
from argus.knowledge.models import Chunk, Document, DocumentCompany
from argus.research import graph as graph_mod
from argus.research import timeline as timeline_mod

STRATEGY_VERSION = "hybrid-rrf/v2"
RRF_K = 60  # standard damping constant
POOL_FACTOR = 3  # each signal contributes k * POOL_FACTOR candidates
DEFAULT_STRATEGIES = ("semantic", "lexical", "graph", "timeline")

_TIMEFRAME_RE = re.compile(r"^(\d{4})(?:(Q[1-4])|-(\d{2}))?$")


@dataclass
class SearchFilters:
    company_id: uuid.UUID | None = None
    doc_types: list[str] | None = None
    sources: list[str] | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    # free-form period ("2024Q3", "2024-06", "2024") gating the timeline strategy
    timeframe: str = ""


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
    # which signals' ranked lists this chunk appeared in, in contribution order
    contributing_strategies: list[str] = field(default_factory=list)


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


def _parse_timeframe(timeframe: str) -> tuple[datetime, datetime] | None:
    """"2024" -> the year; "2024Q3" -> the quarter; "2024-06" -> the month.
    ponytail: covers the common free-form shapes; unrecognized input just
    disables the timeline strategy for this query rather than guessing."""
    m = _TIMEFRAME_RE.match(timeframe.strip())
    if not m:
        return None
    year = int(m.group(1))
    if m.group(2):
        q = int(m.group(2)[1])
        start_month, end_month = (q - 1) * 3 + 1, (q - 1) * 3 + 3
    elif m.group(3):
        start_month = end_month = int(m.group(3))
    else:
        start_month, end_month = 1, 12
    start = datetime(year, start_month, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if end_month == 12
        else datetime(year, end_month + 1, 1, tzinfo=UTC)
    )
    return start, end


def _graph_ids(
    session: Session, filters: SearchFilters, query_embedding: list[float], pool: int
) -> list[uuid.UUID]:
    """Seed = filters.company_id; expand to co-mentioned neighbor companies via the
    knowledge graph, then rank each neighbor's chunks by semantic relevance —
    closer neighbors contribute first. No seed or no neighbors: no rows (RRF just
    fuses over whatever other signals contributed)."""
    if filters.company_id is None:
        return []
    neighbors = graph_mod.neighbor_company_ids(session, filters.company_id)
    if not neighbors:
        return []
    ordered = sorted(neighbors, key=lambda cid: neighbors[cid])
    per = max(1, pool // len(ordered))
    ids: list[uuid.UUID] = []
    for cid in ordered:
        neighbor_filters = replace(filters, company_id=cid)
        found = session.scalars(
            _base_query(neighbor_filters)
            .where(Chunk.embedding.is_not(None))
            .order_by(Chunk.embedding.cosine_distance(query_embedding))
            .limit(per)
        ).all()
        ids.extend(cid2 for cid2 in found if cid2 not in ids)
    return ids[:pool]


def _timeline_ids(session: Session, filters: SearchFilters, pool: int) -> list[uuid.UUID]:
    """Recency-ordered, timeframe-scoped chunks: one representative (first) chunk
    per document, ordered by publication date descending. Requires both a company
    seed and a parseable timeframe; otherwise contributes nothing."""
    if not filters.timeframe or filters.company_id is None:
        return []
    bounds = _parse_timeframe(filters.timeframe)
    if bounds is None:
        return []
    entries = timeline_mod.timeline(
        session, filters.company_id, start=bounds[0], end=bounds[1], limit=pool
    )
    if not entries:
        return []
    doc_ids = [e.document_id for e in entries]
    first_chunk_by_doc = dict(
        session.execute(
            select(Chunk.document_id, Chunk.id).where(
                Chunk.document_id.in_(doc_ids), Chunk.position == 0
            )
        ).all()
    )
    return [first_chunk_by_doc[d] for d in doc_ids if d in first_chunk_by_doc]


def search(
    session: Session,
    query: str,
    filters: SearchFilters | None = None,
    k: int = 10,
    strategies: tuple[str, ...] = DEFAULT_STRATEGIES,
) -> list[RetrievalResult]:
    if not query.strip() or k <= 0:  # ponytail: nothing to rank; avoid empty/zero-limit edge cases
        return []
    filters = filters or SearchFilters()
    pool = k * POOL_FACTOR
    query_embedding = get_provider().embed([query])[0]

    signal_ids: dict[str, list[uuid.UUID]] = {}
    if "semantic" in strategies:
        signal_ids["semantic"] = session.scalars(
            _base_query(filters)
            .where(Chunk.embedding.is_not(None))
            .order_by(Chunk.embedding.cosine_distance(query_embedding))
            .limit(pool)
        ).all()
    if "lexical" in strategies:
        tsquery = func.plainto_tsquery("english", query)
        signal_ids["lexical"] = session.scalars(
            _base_query(filters)
            .where(Chunk.tsv.op("@@")(tsquery))
            .order_by(func.ts_rank(Chunk.tsv, tsquery).desc())
            .limit(pool)
        ).all()
    if "graph" in strategies:
        signal_ids["graph"] = _graph_ids(session, filters, query_embedding, pool)
    if "timeline" in strategies:
        signal_ids["timeline"] = _timeline_ids(session, filters, pool)

    # reciprocal rank fusion across every contributing signal
    ranks: dict[uuid.UUID, dict] = {}
    for signal, ids in signal_ids.items():
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
            contributing_strategies=[
                key[: -len("_rank")] for key in scores if key.endswith("_rank")
            ],
        )
        for cid, scores in top
        for chunk, doc in [rows[cid]]
    ]
