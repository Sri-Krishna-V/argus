"""Orchestrator: DAG compilation, task execution, failure semantics (PRD-V2 1.2/4.1)."""

import uuid

import sqlalchemy as sa

from tests.conftest import requires_db


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
