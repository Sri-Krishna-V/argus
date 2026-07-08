"""Orchestrator: DAG compilation, task execution, failure semantics (PRD-V2 1.2/4.1)."""

import uuid

import sqlalchemy as sa

from argus.core.db import session_scope
from tests.conftest import requires_db

# dilutes term frequency so this fixture doc doesn't skew other modules' ranking
# assertions on the shared test corpus (see tests/test_investigations.py's `corpus`).
FILLER = "Quarterly commentary follows. " + "filler " * 40


@requires_db
def test_investigation_task_defaults_and_fk(db_session):
    from argus.investigations import engine
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "test question")
    db_session.flush()
    task = InvestigationTask(
        investigation_id=inv.id, task_type="collect_evidence", objective="find evidence"
    )
    db_session.add(task)
    db_session.flush()
    assert task.status == "pending"
    assert task.depends_on == []
    assert task.inputs == {} and task.outputs == {}

    orphan = InvestigationTask(
        investigation_id=uuid.uuid4(), task_type="collect_evidence", objective="x"
    )
    db_session.add(orphan)
    import pytest

    with pytest.raises(sa.exc.IntegrityError):
        db_session.flush()
    db_session.rollback()


def _plan(queries=("q1", "q2")):
    from argus.agentruntime.schemas import ResearchPlan

    return ResearchPlan(
        companies=["NVIDIA CORP"], doc_types=["news"],
        queries=list(queries), rationale="canned",
    )


@requires_db
def test_compile_dag_builds_fanout_fanin(db_session):
    from argus.core.models import Job
    from argus.investigations import engine, orchestrator

    inv = engine.create(db_session, "How is the DC business?")
    db_session.flush()
    tasks = orchestrator.compile_dag(db_session, inv, _plan(), company_ids=[])
    db_session.flush()

    collects = [t for t in tasks if t.task_type == "collect_evidence"]
    synths = [t for t in tasks if t.task_type == "synthesize"]
    assert len(collects) == 2 and len(synths) == 1
    assert all(t.depends_on == [] for t in collects)
    assert sorted(synths[0].depends_on) == sorted(str(t.id) for t in collects)
    assert collects[0].inputs["query"] == "q1"

    jobs = db_session.scalars(
        sa.select(Job).where(Job.job_type == orchestrator.JOB_TYPE)
    ).all()
    # only dependency-free tasks are enqueued; synthesize waits
    assert {j.payload["task_id"] for j in jobs} == {str(t.id) for t in collects}
    assert all(j.document_id == inv.id for j in jobs)


@requires_db
def test_compile_dag_rejects_empty_plan(db_session):
    import pytest

    from argus.investigations import engine, orchestrator

    inv = engine.create(db_session, "q")
    db_session.flush()
    with pytest.raises(ValueError, match="no queries"):
        orchestrator.compile_dag(db_session, inv, _plan(queries=()), company_ids=[])


def test_validate_dag_rejects_cycles():
    import pytest

    from argus.investigations.orchestrator import _validate_dag

    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    with pytest.raises(ValueError, match="cycle"):
        _validate_dag({a: [b], b: [a]})


def _register(monkeypatch):
    from argus.dataplatform import worker
    from argus.investigations import orchestrator

    monkeypatch.setitem(worker.EXTRA_HANDLERS, orchestrator.JOB_TYPE, orchestrator.run_task)


@requires_db
def test_dag_executes_to_completed_report(monkeypatch, fake_embeddings, seeded_companies):
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import Evidence, Investigation, InvestigationTask, Report
    from tests.conftest import drain_queue, ingest_html
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    _register(monkeypatch)
    ingest_html(
        f"<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        f"grew strongly this quarter. {FILLER}</p></body></html>", doc_type="news",
    )
    drain_queue()

    with session_scope() as session:
        inv = engine.create(session, "How is the automotive business?")
        inv_id = inv.id
        plan = _plan(queries=("automotive self-driving platform revenue",))
        orchestrator.compile_dag(session, inv, plan,
                                 company_ids=[seeded_companies["NVIDIA CORP"]])

    drain_queue()  # collect fan-out then synthesize fan-in, via the outbox

    with session_scope() as session:
        tasks = session.scalars(
            sa.select(InvestigationTask).where(InvestigationTask.investigation_id == inv_id)
        ).all()
        assert {t.status for t in tasks} == {"complete"}
        collect = next(t for t in tasks if t.task_type == "collect_evidence")
        assert collect.outputs["chunk_ids"]
        assert session.scalar(
            sa.select(sa.func.count()).select_from(Evidence)
            .where(Evidence.investigation_id == inv_id)
        ) > 0
        report = session.scalar(sa.select(Report).where(Report.investigation_id == inv_id))
        assert report is not None
        inv = session.get(Investigation, inv_id)
        assert inv.confidence is not None and 0 < inv.confidence <= 1


@requires_db
def test_synthesize_waits_for_dependencies(monkeypatch, fake_embeddings, db_session):
    """A synthesize job delivered before its deps are complete must raise (job retries)."""
    import pytest

    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "q")
    db_session.flush()
    collect = InvestigationTask(investigation_id=inv.id, task_type="collect_evidence",
                                objective="x", inputs={"query": "q", "company_ids": [],
                                                       "doc_types": [], "k": 2})
    db_session.add(collect)
    db_session.flush()
    synth = InvestigationTask(investigation_id=inv.id, task_type="synthesize",
                              objective="x", depends_on=[str(collect.id)])
    db_session.add(synth)
    db_session.flush()
    job = Job(job_type=orchestrator.JOB_TYPE, document_id=inv.id,
              payload={"task_id": str(synth.id)})
    db_session.add(job)
    db_session.flush()
    with pytest.raises(RuntimeError, match="dependencies not complete"):
        orchestrator.run_task(db_session, job)


@requires_db
def test_completed_task_redelivery_is_noop(monkeypatch, db_session):
    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "q")
    db_session.flush()
    task = InvestigationTask(investigation_id=inv.id, task_type="collect_evidence",
                             objective="x", status="complete")
    db_session.add(task)
    db_session.flush()
    job = Job(job_type=orchestrator.JOB_TYPE, document_id=inv.id,
              payload={"task_id": str(task.id)})
    db_session.add(job)
    db_session.flush()
    orchestrator.run_task(db_session, job)  # must not raise or re-run


@requires_db
def test_exhausted_task_fails_investigation(monkeypatch, fake_embeddings, migrated_db):
    from argus.core import events as core_events
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import Investigation, InvestigationTask
    from tests.conftest import drain_queue

    def boom(session, inv, task):
        # Force the pending `task.status = "running"` write to autoflush before
        # raising, so this test genuinely exercises the row-lock/rollback ordering
        # in orchestrator._fail_if_exhausted (a handler that never touches `session`
        # wouldn't have anything flushed yet, and couldn't catch a regression there).
        session.execute(
            sa.select(InvestigationTask.id).where(InvestigationTask.id == task.id)
        )
        raise RuntimeError("handler exploded")

    monkeypatch.setitem(orchestrator.HANDLERS, "collect_evidence", boom)
    _register(monkeypatch)
    monkeypatch.setattr(core_events, "retry_at",
                        lambda attempts: core_events.func.now())

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        session.flush()
        task = InvestigationTask(investigation_id=inv_id, task_type="collect_evidence",
                                 objective="x", inputs={"query": "q", "company_ids": [],
                                                        "doc_types": [], "k": 2})
        session.add(task)
        session.flush()
        orchestrator._enqueue_task(session, task)

    drain_queue()

    with session_scope() as session:
        task = session.scalars(sa.select(InvestigationTask)
                               .where(InvestigationTask.investigation_id == inv_id)).one()
        assert task.status == "failed"
        assert "handler exploded" in task.error
        assert session.get(Investigation, inv_id).status == "failed"
