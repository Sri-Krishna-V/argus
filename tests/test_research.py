"""Phase 5: hybrid retrieval ranks known-relevant docs top-3; filters, graph hops,
timelines, and citation resolution work on a seeded corpus. Requires Postgres."""

from datetime import UTC, datetime

import pytest

from argus.core.db import session_scope
from argus.research.citations import resolve
from argus.research.graph import neighborhood
from argus.research.retrieval import SearchFilters, search
from argus.research.timeline import timeline
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]

FILler = "Quarterly commentary follows. " + "filler " * 40


_docs: dict | None = None


def _corpus():
    """Three topic-distinct documents, ingested once per module — per-test copies
    would duplicate dates/text and pollute filter assertions."""
    global _docs
    if _docs is not None:
        return _docs
    docs = {
        "datacenter": ingest_html(
            f"<html><body><p>NVIDIA CORP data center revenue grew 400 percent on "
            f"accelerating GPU demand from hyperscalers. {FILler}</p></body></html>",
            published_at=datetime(2026, 6, 1, tzinfo=UTC),
            doc_type="news",
        ),
        "iphone": ingest_html(
            f"<html><body><p>Apple Inc. iPhone shipments slowed in China amid "
            f"competition from domestic handset makers. {FILler}</p></body></html>",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            doc_type="news",
        ),
        "filing": ingest_html(
            f"<html><body><p>Apple Inc. annual report discusses supply chain "
            f"concentration risk and dependency on NVIDIA CORP accelerators. "
            f"{FILler}</p></body></html>",
            published_at=datetime(2026, 4, 1, tzinfo=UTC),
            doc_type="filing",
        ),
    }
    drain_queue()
    _docs = docs
    return docs


def test_hybrid_search_ranks_relevant_doc_top3():
    docs = _corpus()
    with session_scope() as session:
        results = search(session, "data center GPU revenue growth", k=5)
    assert results, "no results"
    assert docs["datacenter"] in [r.document_id for r in results[:3]]
    top = results[0]
    assert top.strategy == "hybrid-rrf/v1"
    assert "rrf" in top.scores and ("lexical_rank" in top.scores or "semantic_rank" in top.scores)


def test_filters_constrain_results(seeded_companies):
    docs = _corpus()
    apple = seeded_companies["Apple Inc."]
    with session_scope() as session:
        by_company = search(
            session, "supply chain risk", filters=SearchFilters(company_id=apple), k=10
        )
        assert docs["datacenter"] not in {r.document_id for r in by_company}

        by_type = search(
            session, "supply chain risk", filters=SearchFilters(doc_types=["filing"]), k=10
        )
        assert {r.doc_type for r in by_type} == {"filing"}

        cutoff = datetime(2026, 5, 15, tzinfo=UTC)
        by_date = search(
            session, "iPhone shipments China", filters=SearchFilters(published_after=cutoff), k=10
        )
        assert docs["iphone"] not in {r.document_id for r in by_date}  # published 05-01
        assert all(r.published_at >= cutoff for r in by_date)


def test_graph_neighborhood_reaches_co_mentioned_company(seeded_companies):
    docs = _corpus()
    hops = None
    with session_scope() as session:
        hops = neighborhood(session, seeded_companies["NVIDIA CORP"], depth=1)
    labels = {h.src_label for h in hops} | {h.dst_label for h in hops}
    assert {"NVIDIA CORP", "Apple Inc."} <= labels
    assert all(h.source_document_id is not None for h in hops)
    assert docs["filing"] in {h.source_document_id for h in hops}


def test_timeline_orders_by_publication(seeded_companies):
    docs = _corpus()
    with session_scope() as session:
        entries = timeline(session, seeded_companies["Apple Inc."])
    ids = [e.document_id for e in entries]
    assert ids.index(docs["iphone"]) < ids.index(docs["filing"])  # newest first
    assert all(e.published_at is not None for e in entries)


def test_citations_resolve_and_missing_chunks_raise():
    import uuid

    _corpus()
    with session_scope() as session:
        results = search(session, "data center GPU revenue", k=3)
        citations = resolve(session, [r.chunk_id for r in results])
        assert len(citations) == len(results)
        assert all(c.url and c.excerpt for c in citations)

        with pytest.raises(LookupError, match="missing chunks"):
            resolve(session, [uuid.uuid4()])
