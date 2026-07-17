"""Phase 5: hybrid retrieval ranks known-relevant docs top-3; filters, graph hops,
timelines, and citation resolution work on a seeded corpus. Requires Postgres.
Phase 3 (PRD-V2 2.1-2.5) extends this with graph/timeline retrieval strategies
fused via RRF, and pure (no-DB) source-ranking tests."""

import uuid
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
    assert top.strategy == "hybrid-rrf/v2"
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
    _corpus()
    with session_scope() as session:
        results = search(session, "data center GPU revenue", k=3)
        citations = resolve(session, [r.chunk_id for r in results])
        assert len(citations) == len(results)
        assert all(c.url and c.excerpt for c in citations)

        with pytest.raises(LookupError, match="missing chunks"):
            resolve(session, [uuid.uuid4()])


# --- PRD-V2 2.2: graph + timeline retrieval strategies fused via RRF ---


def test_search_noop_strategies_contribute_nothing_but_dont_break_fusion():
    """RRF fusion with a strategy returning zero rows (graph/timeline need a company
    filter / timeframe respectively; a bare query has neither) must still rank
    fine on semantic+lexical alone."""
    docs = _corpus()
    with session_scope() as session:
        results = search(session, "data center GPU revenue growth", k=5)
    assert results
    assert docs["datacenter"] in [r.document_id for r in results[:3]]
    assert not any(
        "graph_rank" in r.scores or "timeline_rank" in r.scores for r in results
    )


def test_graph_strategy_surfaces_neighbor_company_chunks(seeded_companies):
    """NVIDIA and Apple are co-mentioned in the "filing" doc; searching seeded on
    NVIDIA should reach Apple-only content (the "iphone" doc) via graph traversal —
    something semantic+lexical alone, filtered to NVIDIA, cannot do."""
    docs = _corpus()
    nvidia = seeded_companies["NVIDIA CORP"]
    with session_scope() as session:
        base_only = search(
            session, "iPhone shipments China", filters=SearchFilters(company_id=nvidia),
            k=10, strategies=("semantic", "lexical"),
        )
        assert docs["iphone"] not in {r.document_id for r in base_only}

        with_graph = search(
            session, "iPhone shipments China", filters=SearchFilters(company_id=nvidia), k=10,
        )
        assert docs["iphone"] in {r.document_id for r in with_graph}
        hit = next(r for r in with_graph if r.document_id == docs["iphone"])
        assert "graph_rank" in hit.scores
        assert "graph" in hit.contributing_strategies


def test_graph_strategy_noop_with_no_edges():
    """An unseeded/unknown company has no graph neighbors: the strategy contributes
    nothing, and search doesn't crash — it just falls back to whatever (nothing,
    here) the base filters allow."""
    with session_scope() as session:
        results = search(
            session, "revenue growth", filters=SearchFilters(company_id=uuid.uuid4()), k=5
        )
    assert results == []


def test_timeline_strategy_boosts_recent_chunks_in_timeframe(seeded_companies):
    docs = _corpus()
    apple = seeded_companies["Apple Inc."]
    with session_scope() as session:
        results = search(
            session, "Apple", filters=SearchFilters(company_id=apple, timeframe="2026-05"), k=10,
        )
    hit = next((r for r in results if r.document_id == docs["iphone"]), None)
    assert hit is not None
    assert "timeline_rank" in hit.scores


def test_timeline_strategy_noop_on_unparseable_timeframe(seeded_companies):
    apple = seeded_companies["Apple Inc."]
    with session_scope() as session:
        results = search(
            session, "Apple", filters=SearchFilters(company_id=apple, timeframe="not-a-date"),
            k=10,
        )
    assert not any("timeline_rank" in r.scores for r in results)


# --- PRD-V2 2.3: deterministic source ranking (pure, no DB) ---


def test_score_source_components_move_score_in_expected_direction():
    from argus.knowledge.models import Document
    from argus.research.ranking import score_source

    now = datetime(2026, 7, 17, tzinfo=UTC)
    filing = Document(doc_type="filing", published_at=now, source="sec_edgar")
    news = Document(doc_type="news", published_at=now, source="rss")
    old_news = Document(
        doc_type="news", published_at=datetime(2020, 1, 1, tzinfo=UTC), source="rss"
    )

    score_filing, explanation = score_source(filing, 0, now)
    score_news, _ = score_source(news, 0, now)
    score_old, _ = score_source(old_news, 0, now)
    score_corroborated, _ = score_source(news, 5, now, corroborating_publishers=5)
    score_echo, _ = score_source(news, 5, now, corroborating_publishers=1)

    assert score_filing > score_news  # authority: filings beat news
    assert score_news > score_old  # freshness: newer beats older
    assert score_corroborated > score_news  # corroboration: more backing beats none
    assert score_corroborated > score_echo  # independence: diverse beats an echo chamber
    assert "components" in explanation and "inputs" in explanation
    assert set(explanation["components"]) == {
        "authority", "freshness", "independence", "corroboration",
    }


def test_score_source_handles_missing_publish_date_and_zero_corroboration():
    from argus.knowledge.models import Document
    from argus.research.ranking import score_source

    now = datetime(2026, 7, 17, tzinfo=UTC)
    undated = Document(doc_type="news", published_at=None, source="rss")
    score, explanation = score_source(undated, 0, now)
    assert 0.0 <= score <= 1.0
    assert explanation["components"]["independence"]["value"] == 0.0
