"""Deterministic pipeline stages (Bible §10: no AI orchestration here).

Each stage is idempotent for (document_id, stage, pipeline_version): derived rows are
deleted and re-created inside the stage's transaction, so replaying a stage converges.
"""

import logging
import re
import uuid

from bs4 import BeautifulSoup
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from argus.core import events
from argus.dataplatform import storage
from argus.dataplatform.embeddings import get_provider
from argus.dataplatform.extraction import CompanyMatcher
from argus.knowledge.models import Chunk, Company, Document, DocumentCompany, EntityMention

log = logging.getLogger(__name__)

STAGES = [
    "parse", "extract_metadata", "extract_entities", "chunk", "embed",
    "build_graph", "validate",
]
_NEXT = dict(zip(STAGES, STAGES[1:] + [None], strict=True))
_EVENT = {
    "parse": "document.parsed",
    "extract_metadata": "document.metadata_extracted",
    "extract_entities": "document.entities_extracted",
    "chunk": "document.chunked",
    "embed": "document.embedded",
    "build_graph": "document.graph_built",
    "validate": "document.enriched",
}

CHUNK_WORD_BUDGET = 250


def run_stage(session: Session, stage: str, document_id: uuid.UUID, pipeline_version: int) -> None:
    doc = session.get(Document, document_id)
    if doc is None:
        raise LookupError(f"document {document_id} not found")
    payload = _HANDLERS[stage](session, doc, pipeline_version) or {}
    events.emit(
        session,
        _EVENT[stage],
        aggregate_id=doc.id,
        payload={"pipeline_version": pipeline_version, **payload},
        next_job=_NEXT[stage],
        job_payload={"pipeline_version": pipeline_version},
    )


def _parse(session: Session, doc: Document, version: int) -> dict:
    raw = storage.read_raw(doc.raw_path)
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    storage.write_parsed(doc.checksum, version, text)
    doc.status = "parsed"
    return {"parsed_chars": len(text)}


def _extract_metadata(session: Session, doc: Document, version: int) -> dict:
    # Connectors supply source metadata; this stage scores extraction quality so gaps
    # are observable rather than silent (metadata is first-class).
    text = storage.read_parsed(doc.checksum, version)
    quality = sum((bool(doc.title), bool(doc.published_at), bool(doc.url), len(text) > 200)) / 4
    return {"extraction_quality": quality}


_matcher: CompanyMatcher | None = None


def _get_matcher(session: Session) -> CompanyMatcher:
    # ponytail: built once per worker process; restart the worker after large
    # company-registry changes (profiles run daily; worker restarts are routine)
    global _matcher
    if _matcher is None:
        rows = session.execute(
            select(Company.id, Company.name, Company.tickers, Company.aliases)
        ).all()
        _matcher = CompanyMatcher([(str(r[0]), r[1], r[2], r[3]) for r in rows])
    return _matcher


def _extract_entities(session: Session, doc: Document, version: int) -> dict:
    text = storage.read_parsed(doc.checksum, version)
    mentions = _get_matcher(session).find(text)

    session.execute(
        delete(EntityMention).where(
            EntityMention.document_id == doc.id, EntityMention.pipeline_version == version
        )
    )
    for m in mentions:
        session.add(
            EntityMention(
                document_id=doc.id,
                mention_text=m.text,
                char_start=m.start,
                char_end=m.end,
                resolved_company_id=uuid.UUID(m.company_id),
                resolution_version=1,
                pipeline_version=version,
            )
        )
    for company_id in {m.company_id for m in mentions}:
        session.merge(
            DocumentCompany(document_id=doc.id, company_id=uuid.UUID(company_id))
        )
    return {"mentions": len(mentions)}


def _chunk(session: Session, doc: Document, version: int) -> dict:
    text = storage.read_parsed(doc.checksum, version)
    session.execute(
        delete(Chunk).where(Chunk.document_id == doc.id, Chunk.pipeline_version == version)
    )
    position = 0
    for start, end, chunk_text in _pack_paragraphs(text):
        session.add(
            Chunk(
                document_id=doc.id,
                position=position,
                text=chunk_text,
                char_start=start,
                char_end=end,
                token_count=len(chunk_text.split()),
                pipeline_version=version,
            )
        )
        position += 1
    return {"chunks": position}


def _pack_paragraphs(text: str) -> list[tuple[int, int, str]]:
    """Greedy paragraph packing to ~CHUNK_WORD_BUDGET words, offsets into parsed text."""
    out: list[tuple[int, int, str]] = []
    start = None
    words = 0
    cursor = 0
    end = 0
    for para in text.split("\n"):
        para_start = text.index(para, cursor) if para else cursor
        cursor = para_start + len(para)
        if not para.strip():
            continue
        if start is None:
            start, words, end = para_start, 0, para_start
        words += len(para.split())
        end = para_start + len(para)
        if words >= CHUNK_WORD_BUDGET:
            out.append((start, end, text[start:end]))
            start = None
    if start is not None and end > start:
        out.append((start, end, text[start:end]))
    return out


def _embed(session: Session, doc: Document, version: int) -> dict:
    chunks = (
        session.execute(
            select(Chunk)
            .where(
                Chunk.document_id == doc.id,
                Chunk.pipeline_version == version,
                Chunk.embedding.is_(None),
            )
            .order_by(Chunk.position)
        )
        .scalars()
        .all()
    )
    if chunks:
        provider = get_provider()
        vectors = provider.embed([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = provider.name
    return {"embedded": len(chunks)}


def _validate(session: Session, doc: Document, version: int) -> dict:
    n_chunks = len(
        session.execute(
            select(Chunk.id).where(
                Chunk.document_id == doc.id, Chunk.pipeline_version == version
            )
        ).all()
    )
    if n_chunks == 0:
        raise ValueError(f"document {doc.id} produced no chunks")
    doc.status = "enriched"
    return {"chunks": n_chunks}


def _build_graph(session: Session, doc: Document, version: int) -> dict:
    from argus.knowledge.graph import build_for_document

    return build_for_document(session, doc.id, version)


_HANDLERS = {
    "parse": _parse,
    "extract_metadata": _extract_metadata,
    "extract_entities": _extract_entities,
    "chunk": _chunk,
    "embed": _embed,
    "build_graph": _build_graph,
    "validate": _validate,
}
