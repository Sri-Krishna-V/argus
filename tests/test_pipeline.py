"""Integration: a fixture document flows ingest → parse → … → validate through the
worker, producing chunks, embeddings, mentions, events, and pipeline_runs; replaying
a stage converges (idempotency). Requires Postgres (make up)."""

import pytest
import sqlalchemy as sa

from argus.core import events
from argus.core.db import session_scope
from argus.core.models import Event, Job
from argus.dataplatform import pipeline
from argus.knowledge.models import Chunk, Document, EntityMention
from argus.observability.models import PipelineRun
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
    monkeypatch.setattr(events, "retry_at", lambda attempts: events.datetime.now(events.UTC))

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
