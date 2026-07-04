"""Temporal knowledge: entity-scoped documents ordered by publication time.
Computed from metadata, not stored (docs/DOMAIN_MODEL.md)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus.knowledge.models import Document, DocumentCompany


@dataclass
class TimelineEntry:
    document_id: uuid.UUID
    published_at: datetime
    title: str | None
    doc_type: str
    source: str
    url: str | None


def timeline(
    session: Session,
    company_id: uuid.UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
) -> list[TimelineEntry]:
    q = (
        select(Document)
        .join(DocumentCompany, DocumentCompany.document_id == Document.id)
        .where(DocumentCompany.company_id == company_id, Document.published_at.is_not(None))
        .order_by(Document.published_at.desc())
        .limit(limit)
    )
    if start:
        q = q.where(Document.published_at >= start)
    if end:
        q = q.where(Document.published_at <= end)
    return [
        TimelineEntry(d.id, d.published_at, d.title, d.doc_type, d.source, d.url)
        for d in session.scalars(q)
    ]
