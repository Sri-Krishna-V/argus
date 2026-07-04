"""Citation assembly: a citation is the guaranteed-resolvable traversal
chunk → document → source URL (ADR-0005). Uncited chunk IDs raise — silently
dropping a citation would let unsupported claims through."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus.knowledge.models import Chunk, Document

EXCERPT_CHARS = 240


@dataclass
class Citation:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None
    url: str | None
    source: str
    published_at: datetime | None
    excerpt: str


def resolve(session: Session, chunk_ids: list[uuid.UUID]) -> list[Citation]:
    rows = {
        chunk.id: (chunk, doc)
        for chunk, doc in session.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(chunk_ids))
        ).all()
    }
    missing = set(chunk_ids) - set(rows)
    if missing:
        raise LookupError(f"citations reference missing chunks: {sorted(missing)}")
    return [
        Citation(
            chunk_id=chunk.id,
            document_id=doc.id,
            title=doc.title,
            url=doc.url,
            source=doc.source,
            published_at=doc.published_at,
            excerpt=chunk.text[:EXCERPT_CHARS],
        )
        for chunk, doc in (rows[cid] for cid in chunk_ids)
    ]
