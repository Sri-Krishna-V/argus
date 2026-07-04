"""Connector framework. Connectors only discover and fetch; the framework owns
dedupe, raw-store writes, event emission, and job creation (docs/RISKS.md #5)."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from argus.core import events
from argus.core.config import get_settings
from argus.dataplatform import storage
from argus.knowledge.models import Document
from argus.knowledge.repositories import DocumentRepository

log = logging.getLogger(__name__)


@dataclass
class DocumentRef:
    source: str
    native_id: str
    doc_type: str
    url: str | None = None
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    inline_content: bytes | None = None  # feeds carry content in the entry itself
    enqueue_pipeline: bool = True  # registry snapshots are provenance, not search corpus
    extra: dict = field(default_factory=dict)


def ingest(session: Session, connector, refs: list[DocumentRef] | None = None) -> dict:
    """Run one connector pass: discover refs, fetch new ones, persist, enqueue parse."""
    repo = DocumentRepository(session)
    version = get_settings().pipeline_version
    seen = new = failed = 0
    for ref in refs if refs is not None else connector.discover():
        seen += 1
        if repo.by_source_id(ref.source, ref.native_id) is not None:
            continue
        try:
            content = ref.inline_content or connector.fetch(ref)
        except Exception:
            failed += 1
            log.exception("fetch failed", extra={"context": {"ref": ref.native_id}})
            continue
        checksum, raw_path = storage.write_raw(content)
        doc = repo.add(
            Document(
                source=ref.source,
                source_native_id=ref.native_id,
                checksum=checksum,
                raw_path=raw_path,
                title=ref.title,
                publisher=ref.publisher,
                url=ref.url,
                doc_type=ref.doc_type,
                published_at=ref.published_at,
                extra=ref.extra,
            )
        )
        events.emit(
            session,
            "document.ingested",
            aggregate_id=doc.id,
            payload={"source": ref.source},
            next_job="parse" if ref.enqueue_pipeline else None,
            job_payload={"pipeline_version": version},
        )
        new += 1
    return {"seen": seen, "new": new, "failed": failed}


def run_connector(session: Session, connector) -> dict:
    """Entry point used by scheduler and CLI; honors a connector-specific run()."""
    if hasattr(connector, "run"):
        return connector.run(session)
    return ingest(session, connector)
