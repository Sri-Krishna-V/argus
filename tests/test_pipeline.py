"""Integration: a fixture document flows ingest → parse → … → validate through the
worker, producing chunks, embeddings, mentions, events, and pipeline_runs; replaying
a stage converges (idempotency). Requires Postgres (make up)."""

import uuid

import pytest
import sqlalchemy as sa

from argus.core import events
from argus.core.db import session_scope
from argus.core.models import Event, Job
from argus.dataplatform import embeddings, pipeline
from argus.dataplatform.connectors.base import DocumentRef, ingest
from argus.knowledge.models import Chunk, Company, Document, EntityMention
from argus.observability.models import PipelineRun
from tests.conftest import requires_db

pytestmark = requires_db

HTML = """<html><head><title>t</title><script>junk()</script></head><body>
<h1>Nvidia Corp beats expectations</h1>
{paras}
</body></html>""".format(
    paras="\n".join(
        f"<p>Paragraph {i}: NVIDIA CORP reported strong results. " + "word " * 60 + "</p>"
        for i in range(10)
    )
)


class StubConnector:
    name = "test_stub"

    def __init__(self, native_id: str):
        self.native_id = native_id

    def discover(self) -> list[DocumentRef]:
        return [
            DocumentRef(
                source="test_stub",
                native_id=self.native_id,
                doc_type="news",
                title="Nvidia beats",
                url="https://example.com/x",
                inline_content=HTML.encode(),
            )
        ]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "_provider", embeddings.FakeProvider())


@pytest.fixture(autouse=True)
def fresh_matcher(db_session):
    if db_session.scalar(sa.select(Company).where(Company.cik == "9990001")) is None:
        # fake ticker: a real one would put this test row on the SEC watchlist
        db_session.add(
            Company(name="NVIDIA CORP", cik="9990001", tickers=["ZZZT"], aliases=["NVIDIA"])
        )
        db_session.commit()
    pipeline._matcher = None


def drain_queue() -> int:
    from argus.dataplatform.worker import run_once

    ran = 0
    while run_once():
        ran += 1
        assert ran < 50, "queue did not drain"
    return ran


def ingest_fixture_doc() -> uuid.UUID:
    native_id = str(uuid.uuid4())
    with session_scope() as session:
        stats = ingest(session, StubConnector(native_id))
        assert stats["new"] == 1
        doc_id = session.scalar(
            sa.select(Document.id).where(Document.source_native_id == native_id)
        )
    return doc_id


def test_document_flows_through_full_pipeline(migrated_db):
    doc_id = ingest_fixture_doc()
    drain_queue()

    with session_scope() as session:
        doc = session.get(Document, doc_id)
        assert doc.status == "enriched"

        chunks = session.scalars(sa.select(Chunk).where(Chunk.document_id == doc_id)).all()
        assert len(chunks) > 1
        assert all(c.embedding is not None for c in chunks)
        assert all(c.embedding_model == "fake/deterministic-sha256" for c in chunks)

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
    doc_id = ingest_fixture_doc()
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
    monkeypatch.setattr(events, "retry_at", lambda attempts: events.datetime.now(events.UTC))

    doc_id = ingest_fixture_doc()
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
