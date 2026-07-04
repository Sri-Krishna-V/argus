"""Search indexes: HNSW for semantic retrieval, GIN for lexical, published_at for
temporal queries (Bible §16: retrieval combines multiple techniques).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")
    op.create_index("ix_documents_published_at", "documents", ["published_at"])
    op.create_index("ix_entity_mentions_company", "entity_mentions", ["resolved_company_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_mentions_company", "entity_mentions")
    op.drop_index("ix_documents_published_at", "documents")
    op.execute("DROP INDEX ix_chunks_tsv")
    op.execute("DROP INDEX ix_chunks_embedding_hnsw")
