"""Integration: a fixture document flows ingest → parse → … → validate through the
worker, producing chunks, embeddings, mentions, events, and pipeline_runs; replaying
a stage converges (idempotency). Requires Postgres (make up)."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from argus.core import events
from argus.core.db import session_scope
from argus.core.models import Event, Job
from argus.dataplatform import pipeline, storage
from argus.dataplatform.connectors.base import DocumentRef, run_connector
from argus.knowledge.models import Chunk, Document, EntityMention
from argus.observability.models import PipelineRun
from argus.research.retrieval import search
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]

HTML = """<html><head><title>t</title><script>junk()</script></head><body>
<h1>Nvidia Corp beats expectations</h1>
{paras}
</body></html>""".format(
    paras="\n".join(
        f"<p>Paragraph {i}: NVIDIA CORP reported strong results. " + "word " * 60 + "</p>"
        for i in range(10)
    )
)


def test_document_flows_through_full_pipeline(migrated_db):
    doc_id = ingest_html(HTML)
    drain_queue()

    with session_scope() as session:
        doc = session.get(Document, doc_id)
        assert doc.status == "enriched"

        chunks = session.scalars(sa.select(Chunk).where(Chunk.document_id == doc_id)).all()
        assert len(chunks) > 1
        assert all(c.embedding is not None for c in chunks)
        assert all(c.embedding_model == "fake/feature-hash-bow" for c in chunks)

        mentions = session.scalars(
            sa.select(EntityMention).where(EntityMention.document_id == doc_id)
        ).all()
        assert mentions and all(m.resolved_company_id is not None for m in mentions)

        event_types = set(
            session.scalars(sa.select(Event.event_type).where(Event.aggregate_id == doc_id))
        )
        assert {"document.ingested", "document.parsed", "document.enriched"} <= event_types

        runs = session.scalars(
            sa.select(PipelineRun).where(PipelineRun.document_id == doc_id)
        ).all()
        assert {r.stage for r in runs} == set(pipeline.STAGES)
        assert all(r.status == "success" for r in runs)


def test_stage_replay_is_idempotent(migrated_db):
    doc_id = ingest_html(HTML)
    drain_queue()

    with session_scope() as session:
        before = session.scalars(sa.select(Chunk.id).where(Chunk.document_id == doc_id)).all()
        events.enqueue(session, "chunk", document_id=doc_id, payload={"pipeline_version": 1})
    drain_queue()

    with session_scope() as session:
        after = session.scalars(sa.select(Chunk.id).where(Chunk.document_id == doc_id)).all()
        assert len(after) == len(before)


def test_failing_job_retries_then_dead_letters(migrated_db, monkeypatch):
    from argus.dataplatform import worker

    def boom(*args, **kwargs):
        raise RuntimeError("stage exploded")

    monkeypatch.setitem(pipeline._HANDLERS, "parse", boom)
    # a past timestamp keeps the retried job immediately claimable even if the
    # wall clock steps backward between attempts (WSL2)
    monkeypatch.setattr(
        events, "retry_at", lambda attempts: datetime.now(UTC) - timedelta(hours=1)
    )

    doc_id = ingest_html(HTML)
    for _ in range(3):
        assert worker.run_once()

    with session_scope() as session:
        job = session.scalar(
            sa.select(Job).where(Job.document_id == doc_id, Job.job_type == "parse")
        )
        assert job.status == "dead"
        assert job.attempts == 3
        assert "stage exploded" in job.last_error
        dead_event = session.scalar(
            sa.select(Event).where(
                Event.aggregate_id == doc_id, Event.event_type == "job.dead"
            )
        )
        assert dead_event is not None


class _FakeWireConnector:
    """Minimal Connector: discover() returns refs with no inline content, so
    ingest() must call fetch() — the path StubConnector's inline_content skips."""

    name = "fake_wire"

    def __init__(self, native_id: str, html: bytes):
        self.native_id, self.html = native_id, html

    def discover(self) -> list[DocumentRef]:
        return [
            DocumentRef(
                source=self.name,
                native_id=self.native_id,
                doc_type="news",
                title="fake wire story",
                url="https://example.com/fake-wire",
            )
        ]

    def fetch(self, ref: DocumentRef) -> bytes:
        return self.html


def test_connector_framework_ingests_dedupes_and_is_searchable(migrated_db):
    """End-to-end through the real connector framework (base.run_connector), not
    the ingest_html test shortcut: exercises discover -> fetch -> dedupe -> raw
    store -> pipeline -> search, and confirms a second pass doesn't double-ingest."""
    connector = _FakeWireConnector("fake-wire-1", HTML.encode())

    with session_scope() as session:
        assert run_connector(session, connector) == {"seen": 1, "new": 1, "failed": 0}
    drain_queue()

    with session_scope() as session:
        doc = session.scalar(
            sa.select(Document).where(Document.source_native_id == "fake-wire-1")
        )
        assert doc is not None and doc.status == "enriched"
        assert doc.checksum and storage.read_raw(doc.raw_path)  # raw store round-trips

        chunks = session.scalars(sa.select(Chunk).where(Chunk.document_id == doc.id)).all()
        assert chunks and all(c.embedding is not None for c in chunks)

        results = search(session, "Nvidia Corp expectations")
        assert any(r.document_id == doc.id for r in results)

    # dedupe: replaying the same discover() output must not create a second document
    with session_scope() as session:
        assert run_connector(session, connector) == {"seen": 1, "new": 0, "failed": 0}
        count = session.scalar(
            sa.select(sa.func.count(Document.id)).where(
                Document.source_native_id == "fake-wire-1"
            )
        )
        assert count == 1
