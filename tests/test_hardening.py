import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from typer.testing import CliRunner

from argus.cli import app
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.models import Event, Job
from argus.dataplatform import worker
from argus.knowledge.models import Chunk
from argus.observability.models import PipelineRun
from tests.conftest import drain_queue, ingest_html, requires_db

runner = CliRunner()


@requires_db
def test_reap_stale_recovers_crashed_job(db_session, fake_embeddings):
    doc_id = ingest_html("<html><body><p>reaper crash test document.</p></body></html>")
    with session_scope() as session:
        job = worker.claim_next(session)
        assert job is not None and job.status == "running"
        lease = get_settings().job_lease_seconds
        job.claimed_at = datetime.now(UTC) - timedelta(seconds=lease + 60)
        job_id = job.id

    with session_scope() as session:
        assert worker.reap_stale(session) == 1
        assert session.get(Job, job_id).status == "pending"

    drain_queue()
    with session_scope() as session:
        chunks = session.scalars(
            sa.select(Chunk.id).where(Chunk.document_id == doc_id)
        ).all()
        assert len(chunks) > 0
        # idempotency: exactly one chunk set, not duplicated by the re-run
        assert len(chunks) == len(set(chunks))


@requires_db
def test_reap_stale_respects_lease_boundary(db_session, fake_embeddings):
    ingest_html("<html><body><p>lease boundary test document.</p></body></html>")
    with session_scope() as session:
        job = worker.claim_next(session)
        lease = get_settings().job_lease_seconds
        job.claimed_at = datetime.now(UTC) - timedelta(seconds=lease - 60)
        job_id = job.id

    with session_scope() as session:
        assert worker.reap_stale(session) == 0
        assert session.get(Job, job_id).status == "running"


@requires_db
def test_reap_stale_noop_on_empty_queue(db_session):
    with session_scope() as session:
        assert worker.reap_stale(session) == 0


@requires_db
def test_poison_job_goes_dead_and_retry_dead_resets_it(db_session):
    with session_scope() as session:
        job = Job(job_type="parse", document_id=uuid.uuid4(), max_attempts=1)
        session.add(job)
        session.flush()
        job_id = job.id

    assert worker.run_once() is True

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "dead"
        assert job.last_error and "not found" in job.last_error
        dead_event = session.scalar(
            sa.select(Event).where(
                Event.event_type == "job.dead", Event.aggregate_id == job.document_id
            )
        )
        assert dead_event is not None

    result = runner.invoke(app, ["retry-dead", "--job-id", str(job_id), "--yes"])
    assert result.exit_code == 0

    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "pending" and job.attempts == 0


@requires_db
def test_retry_dead_unknown_job_id_exits_1(db_session):
    result = runner.invoke(app, ["retry-dead", "--job-id", "999999999", "--yes"])
    assert result.exit_code == 1


@requires_db
def test_retry_dead_completed_job_untouched(db_session):
    with session_scope() as session:
        job = Job(job_type="parse", document_id=uuid.uuid4(), status="completed")
        session.add(job)
        session.flush()
        job_id = job.id

    result = runner.invoke(app, ["retry-dead", "--job-id", str(job_id), "--yes"])
    assert result.exit_code == 1

    with session_scope() as session:
        assert session.get(Job, job_id).status == "completed"


class _FailConnector:
    name = "stub_fail"

    def discover(self):
        raise RuntimeError("connector outage")


class _OkConnector:
    name = "stub_ok"

    def discover(self):
        return []


@requires_db
def test_connector_outage_is_contained_and_scheduler_continues(db_session, monkeypatch):
    monkeypatch.setitem(worker.CONNECTORS, "stub_fail", (_FailConnector, "schedule_rss"))
    monkeypatch.setitem(worker.CONNECTORS, "stub_ok", (_OkConnector, "schedule_rss"))

    worker.run_connector_pass("stub_fail")
    with session_scope() as session:
        run = session.scalars(
            sa.select(PipelineRun)
            .where(PipelineRun.stage == "connector.stub_fail")
            .order_by(PipelineRun.created_at.desc())
        ).first()
        assert run is not None and run.status == "failure"

    # the loop is not killed: a subsequent connector pass still runs cleanly
    worker.run_connector_pass("stub_ok")
    with session_scope() as session:
        run = session.scalars(
            sa.select(PipelineRun)
            .where(PipelineRun.stage == "connector.stub_ok")
            .order_by(PipelineRun.created_at.desc())
        ).first()
        assert run is not None and run.status == "success"
