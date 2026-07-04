"""Connector framework. Connectors only discover and fetch; the framework owns
dedupe, raw-store writes, event emission, and job creation (docs/RISKS.md #5)."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from argus.core import events
from argus.core.config import get_settings
from argus.dataplatform import storage
from argus.knowledge.models import Document
from argus.knowledge.repositories import DocumentRepository

log = logging.getLogger(__name__)


def fetch_bytes(
    client: httpx.Client | None,
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 30,
    follow_redirects: bool = False,
) -> bytes:
    """Streaming GET capped at settings.max_fetch_bytes — a single oversized or
    malicious response must never be buffered whole. Raises ValueError past the cap;
    raise_for_status() surfaces non-2xx. Pass an existing client to reuse its
    headers/timeout, or None for a one-off request."""
    limit = get_settings().max_fetch_bytes
    stream_cm = (
        client.stream("GET", url, follow_redirects=follow_redirects)
        if client is not None
        else httpx.stream(
            "GET", url, headers=headers, timeout=timeout, follow_redirects=follow_redirects
        )
    )
    with stream_cm as resp:
        resp.raise_for_status()
        buf = bytearray()
        for chunk in resp.iter_bytes():
            buf += chunk
            if len(buf) > limit:
                raise ValueError(f"response for {url} exceeded max_fetch_bytes cap ({limit})")
        return bytes(buf)


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
