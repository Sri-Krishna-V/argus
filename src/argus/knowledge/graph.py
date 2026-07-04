"""Knowledge graph construction (Bible §18: relationships are intelligence).

V1 edges are derived from resolved document–company links: company nodes plus
co_mentioned edges between companies appearing in the same document. Every edge
carries the source document (provenance is schema-enforced NOT NULL)."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from argus.knowledge.models import Company, DocumentCompany, GraphEdge, GraphNode

# ponytail: pairwise edges are quadratic; a doc mentioning half the index is a
# ticker page, not a relationship signal. Raise/replace with salience weighting
# when co-mention noise shows up in retrieval evals.
MAX_CO_MENTION_COMPANIES = 12


def ensure_company_node(session: Session, company: Company) -> GraphNode:
    key = f"company:{company.cik or company.id}"
    node = session.scalar(
        select(GraphNode).where(
            GraphNode.node_type == "company", GraphNode.canonical_key == key
        )
    )
    if node is None:
        node = GraphNode(
            node_type="company", canonical_key=key, label=company.name, company_id=company.id
        )
        session.add(node)
        session.flush()
    return node


def build_for_document(session: Session, document_id: uuid.UUID, pipeline_version: int) -> dict:
    """Idempotent: rebuilds this document's edges for the given pipeline version."""
    companies = (
        session.scalars(
            select(Company)
            .join(DocumentCompany, DocumentCompany.company_id == Company.id)
            .where(DocumentCompany.document_id == document_id)
            .order_by(Company.id)
        )
        .unique()
        .all()
    )
    nodes = [ensure_company_node(session, c) for c in companies]

    session.execute(
        delete(GraphEdge).where(
            GraphEdge.source_document_id == document_id,
            GraphEdge.pipeline_version == pipeline_version,
        )
    )
    edges = 0
    if 2 <= len(nodes) <= MAX_CO_MENTION_COMPANIES:
        for i, src in enumerate(nodes):
            for dst in nodes[i + 1 :]:
                session.add(
                    GraphEdge(
                        src_node_id=src.id,
                        dst_node_id=dst.id,
                        edge_type="co_mentioned",
                        source_document_id=document_id,
                        pipeline_version=pipeline_version,
                    )
                )
                edges += 1
    return {"nodes": len(nodes), "edges": edges}
