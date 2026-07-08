"""Worker extension point: non-pipeline job types run via EXTRA_HANDLERS."""

import uuid

import sqlalchemy as sa

from argus.core import events
from argus.core.db import session_scope
from argus.core.models import Job
from argus.dataplatform import worker
from tests.conftest import requires_db


@requires_db
def test_extra_handler_executes_and_completes(migrated_db, monkeypatch):
    seen = []
    monkeypatch.setitem(worker.EXTRA_HANDLERS, "test.noop",
                        lambda session, job: seen.append(job.payload["x"]))
    with session_scope() as session:
        events.enqueue(session, "test.noop", payload={"x": 42})
    assert worker.run_once() is True
    assert seen == [42]
    with session_scope() as session:
        job = session.scalar(sa.select(Job).where(Job.job_type == "test.noop"))
        assert job.status == "completed"


@requires_db
def test_unknown_job_type_still_dead_letters(migrated_db):
    with session_scope() as session:
        job = events.enqueue(session, "no.such.type")
        job.max_attempts = 1
    assert worker.run_once() is True
    with session_scope() as session:
        job = session.scalar(sa.select(Job).where(Job.job_type == "no.such.type"))
        assert job.status == "dead"
        assert "unknown job type" in job.last_error


@requires_db
def test_claim_next_document_id_filter(migrated_db):
    target = uuid.uuid4()
    with session_scope() as session:
        events.enqueue(session, "test.noop", document_id=uuid.uuid4())
        events.enqueue(session, "test.noop", document_id=target)
    with session_scope() as session:
        job = worker.claim_next(session, document_id=target)
        assert job is not None and job.document_id == target
        assert worker.claim_next(session, document_id=target) is None  # only one
