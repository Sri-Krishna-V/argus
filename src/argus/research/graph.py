"""Graph traversal: depth-limited neighborhood expansion over typed edges via a
recursive CTE. Returns edges with their source-document provenance intact."""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class GraphHop:
    src_label: str
    dst_label: str
    edge_type: str
    depth: int
    source_document_id: uuid.UUID


def neighborhood(
    session: Session,
    company_id: uuid.UUID,
    depth: int = 2,
    edge_types: list[str] | None = None,
) -> list[GraphHop]:
    type_filter = "AND e.edge_type = ANY(:edge_types)" if edge_types else ""
    rows = session.execute(
        text(f"""
            WITH RECURSIVE walk(node_id, depth) AS (
                SELECT id, 0 FROM graph_nodes WHERE company_id = :company_id
                UNION
                SELECT CASE WHEN e.src_node_id = w.node_id
                            THEN e.dst_node_id ELSE e.src_node_id END,
                       w.depth + 1
                FROM graph_edges e
                JOIN walk w ON w.node_id IN (e.src_node_id, e.dst_node_id)
                WHERE w.depth < :depth {type_filter}
            )
            SELECT DISTINCT ns.label AS src_label, nd.label AS dst_label,
                   e.edge_type, w.depth, e.source_document_id
            FROM graph_edges e
            JOIN walk w ON w.node_id IN (e.src_node_id, e.dst_node_id)
            JOIN graph_nodes ns ON ns.id = e.src_node_id
            JOIN graph_nodes nd ON nd.id = e.dst_node_id
            {"WHERE e.edge_type = ANY(:edge_types)" if edge_types else ""}
            ORDER BY w.depth, e.edge_type
        """),
        {"company_id": company_id, "depth": depth, "edge_types": edge_types},
    ).all()
    return [GraphHop(*row) for row in rows]
