"""Phase 4: entity resolution converges on canonical IDs (the Bible's NVIDIA test),
graph edges carry provenance, search indexes exist. Requires Postgres (make up)."""

import pytest
import sqlalchemy as sa

from argus.core import events
from argus.core.db import session_scope
from argus.knowledge.models import EntityMention, GraphEdge, GraphNode
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]

PARA = "Results were solid this quarter. " + "word " * 40


def _mention_company_ids(doc_id) -> set:
    with session_scope() as session:
        return set(
            session.scalars(
                sa.select(EntityMention.resolved_company_id).where(
                    EntityMention.document_id == doc_id
                )
            )
        )


def test_nvidia_resolves_to_one_canonical_entity_across_sources(migrated_db, seeded_companies):
    """A news article saying 'Nvidia Corp' and a wire item saying '$ZZZT' must land on
    the same canonical company."""
    doc_a = ingest_html(f"<html><body><p>Nvidia Corp beat estimates. {PARA}</p></body></html>")
    doc_b = ingest_html(f"<html><body><p>Traders piled into $ZZZT. {PARA}</p></body></html>")
    drain_queue()

    ids_a, ids_b = _mention_company_ids(doc_a), _mention_company_ids(doc_b)
    assert ids_a == ids_b == {seeded_companies["NVIDIA CORP"]}


def test_co_mention_edges_carry_provenance_and_rebuild_idempotently(migrated_db):
    doc_id = ingest_html(
        f"<html><body><p>Apple Inc. is a large NVIDIA CORP customer. {PARA}</p></body></html>"
    )
    drain_queue()

    with session_scope() as session:
        edges = session.scalars(
            sa.select(GraphEdge).where(GraphEdge.source_document_id == doc_id)
        ).all()
        assert len(edges) == 1
        assert edges[0].edge_type == "co_mentioned"
        node_labels = {
            session.get(GraphNode, edges[0].src_node_id).label,
            session.get(GraphNode, edges[0].dst_node_id).label,
        }
        assert node_labels == {"Apple Inc.", "NVIDIA CORP"}

        events.enqueue(
            session, "build_graph", document_id=doc_id, payload={"pipeline_version": 1}
        )
    drain_queue()

    with session_scope() as session:
        count = session.scalar(
            sa.select(sa.func.count())
            .select_from(GraphEdge)
            .where(GraphEdge.source_document_id == doc_id)
        )
        assert count == 1


def test_search_indexes_exist(migrated_db):
    with migrated_db.connect() as conn:
        names = set(
            conn.scalars(sa.text("select indexname from pg_indexes where tablename='chunks'"))
        )
    assert {"ix_chunks_embedding_hnsw", "ix_chunks_tsv"} <= names
