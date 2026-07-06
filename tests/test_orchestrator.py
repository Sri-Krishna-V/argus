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
