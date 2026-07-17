"""V2 Phase 2: lifecycle state machine, pause/resume/archive/branch endpoints,
annotations, and evidence approve/reject (PRD-V2 1.4, 4.7)."""

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations import engine, lifecycle, orchestrator
from argus.investigations.models import (
    Evidence,
    Investigation,
    InvestigationEvent,
    InvestigationLink,
    InvestigationTask,
)
from argus.knowledge.models import Chunk
from argus.main import app
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = requires_db

FILLER = "Quarterly commentary follows. " + "filler " * 40


@pytest.fixture
def client():
    return TestClient(app)


def _plan(queries=("q1", "q2")):
    from argus.agentruntime.schemas import ResearchPlan

    return ResearchPlan(
        companies=["NVIDIA CORP"], doc_types=["news"], queries=list(queries), rationale="canned",
    )


# --- lifecycle.transition: the state machine itself ---


@pytest.mark.parametrize(
    "start,target",
    [
        ("created", "running"),
        ("created", "paused"),
        ("created", "cancelled"),
        ("running", "paused"),
        ("running", "complete"),
        ("running", "failed"),
        ("running", "cancelled"),
        ("paused", "running"),
        ("paused", "cancelled"),
        ("complete", "archived"),
        ("failed", "archived"),
        ("cancelled", "archived"),
    ],
)
def test_valid_transitions(db_session, start, target):
    inv = engine.create(db_session, "q")
    inv.status = start
    db_session.flush()
    lifecycle.transition(db_session, inv, target)
    assert inv.status == target


@pytest.mark.parametrize(
    "start,target",
    [
        ("complete", "running"),
        ("complete", "paused"),
        ("archived", "running"),
        ("archived", "complete"),
        ("paused", "complete"),
        ("paused", "archived"),
        ("created", "archived"),
        ("running", "archived"),
    ],
)
def test_invalid_transitions_raise(db_session, start, target):
    inv = engine.create(db_session, "q")
    inv.status = start
    db_session.flush()
    with pytest.raises(ValueError, match="cannot transition"):
        lifecycle.transition(db_session, inv, target)
    assert inv.status == start  # rejected transition leaves status untouched


def test_transition_emits_investigation_event(db_session):
    inv = engine.create(db_session, "q")
    inv.status = "running"
    db_session.flush()
    lifecycle.transition(db_session, inv, "paused", {"reason": "test"})
    event = db_session.scalars(
        sa.select(InvestigationEvent)
        .where(InvestigationEvent.investigation_id == inv.id,
               InvestigationEvent.event_type == "investigation.paused")
    ).one()
    assert event.payload == {"reason": "test"}


# --- pause / resume / archive endpoints ---


def _investigation(status: str = "running") -> uuid.UUID:
    with session_scope() as session:
        inv = engine.create(session, "lifecycle endpoint check")
        inv.status = status
        session.flush()
        return inv.id


def test_pause_running_investigation(client):
    inv_id = _investigation("running")
    r = client.post(f"/api/investigations/{inv_id}/pause")
    assert r.status_code == 200
    assert r.json()["status"] == "paused"


def test_pause_created_investigation(client):
    inv_id = _investigation("created")
    r = client.post(f"/api/investigations/{inv_id}/pause")
    assert r.status_code == 200
    assert r.json()["status"] == "paused"


def test_pause_complete_investigation_is_409(client):
    inv_id = _investigation("complete")
    assert client.post(f"/api/investigations/{inv_id}/pause").status_code == 409


def test_pause_unknown_investigation_is_404(client):
    assert client.post(f"/api/investigations/{uuid.uuid4()}/pause").status_code == 404


def test_resume_paused_investigation(client):
    inv_id = _investigation("paused")
    r = client.post(f"/api/investigations/{inv_id}/resume")
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_resume_non_paused_is_409(client):
    inv_id = _investigation("running")
    assert client.post(f"/api/investigations/{inv_id}/resume").status_code == 409


def test_resume_unknown_investigation_is_404(client):
    assert client.post(f"/api/investigations/{uuid.uuid4()}/resume").status_code == 404


def test_archive_complete_investigation(client):
    inv_id = _investigation("complete")
    r = client.post(f"/api/investigations/{inv_id}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_archive_running_investigation_is_409(client):
    inv_id = _investigation("running")
    assert client.post(f"/api/investigations/{inv_id}/archive").status_code == 409


def test_archive_unknown_investigation_is_404(client):
    assert client.post(f"/api/investigations/{uuid.uuid4()}/archive").status_code == 404


# --- pause blocks dependent enqueue; resume re-enqueues and lets it finish ---


def test_pause_blocks_dependent_enqueue_then_resume_completes(client, monkeypatch):
    """Two collect tasks fan into one synthesize task. Pausing right after compile
    (before the collects run) must stop synthesize from ever being enqueued once its
    deps complete; resuming must re-enqueue it via the derived-readiness path."""

    def fake_collect(session, inv, task):
        task.outputs = {"chunk_ids": [], "evidence_count": 0}

    def fake_synthesize(session, inv, task):
        inv.confidence = 1.0
        task.outputs = {"done": True}

    monkeypatch.setitem(orchestrator.HANDLERS, "collect_evidence", fake_collect)
    monkeypatch.setitem(orchestrator.HANDLERS, "synthesize", fake_synthesize)

    with session_scope() as session:
        inv = engine.create(session, "pause mid-flight")
        inv.status = "running"
        session.flush()
        tasks = orchestrator.compile_dag(session, inv, _plan(), company_ids=[])
        inv_id = inv.id
        synth_id = next(t.id for t in tasks if t.task_type == "synthesize")

    r = client.post(f"/api/investigations/{inv_id}/pause")
    assert r.status_code == 200

    drain_queue()  # runs the already-enqueued collect jobs

    with session_scope() as session:
        synth = session.get(InvestigationTask, synth_id)
        assert synth.status == "pending"  # deps complete, but never enqueued — paused
        jobs = session.scalars(
            sa.select(Job).where(Job.job_type == orchestrator.JOB_TYPE)
        ).all()
        assert not any(j.payload.get("task_id") == str(synth_id) for j in jobs)

    r = client.post(f"/api/investigations/{inv_id}/resume")
    assert r.status_code == 200
    assert r.json()["status"] == "running"

    drain_queue()

    with session_scope() as session:
        synth = session.get(InvestigationTask, synth_id)
        assert synth.status == "complete"
        result = engine._finalize(session, inv_id)
        assert result.status == "complete"


# --- branch ---


def test_branch_creates_new_investigation_and_link(client):
    with session_scope() as session:
        parent = engine.create(session, "parent question")
        parent.company_ids = [str(uuid.uuid4())]
        parent_id = parent.id
        parent_company_ids = parent.company_ids

    r = client.post(f"/api/investigations/{parent_id}/branch", json={})
    assert r.status_code == 201
    child = r.json()
    assert child["status"] == "created"
    assert child["question"] == "parent question"
    assert child["id"] != str(parent_id)

    with session_scope() as session:
        child_row = session.get(Investigation, uuid.UUID(child["id"]))
        assert child_row.company_ids == parent_company_ids
        link = session.scalars(
            sa.select(InvestigationLink).where(
                InvestigationLink.src_investigation_id == child_row.id,
                InvestigationLink.dst_investigation_id == parent_id,
            )
        ).one()
        assert link.link_type == "branched_from"


def test_branch_with_explicit_question_overrides_default(client):
    with session_scope() as session:
        parent = engine.create(session, "parent question")
        parent_id = parent.id

    r = client.post(f"/api/investigations/{parent_id}/branch", json={"question": "new angle"})
    assert r.status_code == 201
    assert r.json()["question"] == "new angle"


def test_branch_does_not_copy_evidence_or_tasks(client):
    with session_scope() as session:
        parent = engine.create(session, "parent question")
        parent.status = "running"
        session.flush()
        orchestrator.compile_dag(session, parent, _plan(), company_ids=[])
        parent_id = parent.id

    r = client.post(f"/api/investigations/{parent_id}/branch", json={})
    child_id = uuid.UUID(r.json()["id"])

    with session_scope() as session:
        task_count = session.scalar(
            sa.select(sa.func.count()).select_from(InvestigationTask)
            .where(InvestigationTask.investigation_id == child_id)
        )
        assert task_count == 0


def test_branch_unknown_parent_is_404(client):
    assert client.post(
        f"/api/investigations/{uuid.uuid4()}/branch", json={}
    ).status_code == 404


# --- annotations ---


def test_annotation_post_get_roundtrip(client):
    inv_id = _investigation("running")
    r = client.post(
        f"/api/investigations/{inv_id}/annotations",
        json={"target": {"kind": "investigation", "id": str(inv_id)}, "body": "worth a look"},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["body"] == "worth a look"

    listed = client.get(f"/api/investigations/{inv_id}/annotations").json()
    assert len(listed) == 1
    assert listed[0]["body"] == "worth a look"
    assert listed[0]["target"] == {"kind": "investigation", "id": str(inv_id)}

    with session_scope() as session:
        event = session.scalars(
            sa.select(InvestigationEvent).where(
                InvestigationEvent.investigation_id == inv_id,
                InvestigationEvent.event_type == "analyst.annotated",
            )
        ).one()
        assert event.payload["annotation_id"] == created["id"]


def test_annotation_post_unknown_investigation_is_404(client):
    r = client.post(
        f"/api/investigations/{uuid.uuid4()}/annotations",
        json={"target": {}, "body": "x"},
    )
    assert r.status_code == 404


def test_annotation_get_unknown_investigation_is_404(client):
    assert client.get(f"/api/investigations/{uuid.uuid4()}/annotations").status_code == 404


def test_annotation_empty_body_is_422(client):
    inv_id = _investigation("running")
    r = client.post(
        f"/api/investigations/{inv_id}/annotations", json={"target": {}, "body": ""}
    )
    assert r.status_code == 422


# --- evidence approve/reject ---


def _evidence_row(investigation_id: uuid.UUID, chunk_id, document_id, **overrides) -> uuid.UUID:
    with session_scope() as session:
        ev = Evidence(
            investigation_id=investigation_id, chunk_id=chunk_id, document_id=document_id,
            stance="supporting", rationale="r", query="q", excerpt="e", scores={}, strategy="s",
            **overrides,
        )
        session.add(ev)
        session.flush()
        return ev.id


def _doc_and_chunk(text: str):
    doc_id = ingest_html(f"<html><body><p>{text} {FILLER}</p></body></html>", doc_type="news")
    drain_queue()
    with session_scope() as session:
        chunk_id = session.scalar(
            sa.select(Chunk.id).where(Chunk.document_id == doc_id).limit(1)
        )
        return doc_id, chunk_id


@pytest.mark.usefixtures("fake_embeddings", "seeded_companies")
def test_review_evidence_approve_and_reject(client):
    inv_id = _investigation("running")
    doc_id, chunk_id = _doc_and_chunk("ZZZT NVIDIA CORP evidence review fixture document.")
    ev_id = _evidence_row(inv_id, chunk_id, doc_id)

    r = client.post(
        f"/api/investigations/{inv_id}/evidence/{ev_id}/review", json={"review": "approved"}
    )
    assert r.status_code == 200
    assert r.json()["review"] == "approved"

    r = client.post(
        f"/api/investigations/{inv_id}/evidence/{ev_id}/review", json={"review": "rejected"}
    )
    assert r.status_code == 200
    assert r.json()["review"] == "rejected"

    with session_scope() as session:
        event = session.scalars(
            sa.select(InvestigationEvent).where(
                InvestigationEvent.investigation_id == inv_id,
                InvestigationEvent.event_type == "analyst.evidence_reviewed",
            )
        ).all()
        assert event[-1].payload == {"evidence_id": str(ev_id), "review": "rejected"}


@pytest.mark.usefixtures("fake_embeddings", "seeded_companies")
def test_review_evidence_not_in_investigation_is_404(client):
    inv_id = _investigation("running")
    other_inv_id = _investigation("running")
    doc_id, chunk_id = _doc_and_chunk("ZZZT NVIDIA CORP other investigation fixture.")
    ev_id = _evidence_row(other_inv_id, chunk_id, doc_id)

    r = client.post(
        f"/api/investigations/{inv_id}/evidence/{ev_id}/review", json={"review": "approved"}
    )
    assert r.status_code == 404


def test_review_evidence_unknown_id_is_404(client):
    inv_id = _investigation("running")
    r = client.post(
        f"/api/investigations/{inv_id}/evidence/{uuid.uuid4()}/review",
        json={"review": "approved"},
    )
    assert r.status_code == 404


@pytest.mark.usefixtures("fake_embeddings", "seeded_companies")
def test_review_evidence_invalid_value_is_422(client):
    inv_id = _investigation("running")
    doc_id, chunk_id = _doc_and_chunk("ZZZT NVIDIA CORP invalid review value fixture.")
    ev_id = _evidence_row(inv_id, chunk_id, doc_id)
    r = client.post(
        f"/api/investigations/{inv_id}/evidence/{ev_id}/review", json={"review": "maybe"}
    )
    assert r.status_code == 422


@pytest.mark.usefixtures("fake_embeddings", "seeded_companies")
def test_rejected_evidence_excluded_from_confidence_and_citation(monkeypatch):
    """Rejected evidence must not feed confidence or the drafted narrative; approved
    and never-reviewed (NULL) evidence must still be included."""
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    doc_rejected, chunk_rejected = _doc_and_chunk(
        "ZZZT NVIDIA CORP rejected evidence datacenter commentary."
    )
    doc_kept, chunk_kept = _doc_and_chunk(
        "ZZZT NVIDIA CORP kept evidence automotive commentary."
    )

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        session.add(Evidence(
            investigation_id=inv_id, chunk_id=chunk_rejected, document_id=doc_rejected,
            stance="supporting", rationale="r", query="q", excerpt="e", scores={},
            strategy="s", review="rejected",
        ))
        session.add(Evidence(
            investigation_id=inv_id, chunk_id=chunk_kept, document_id=doc_kept,
            stance="supporting", rationale="r", query="q", excerpt="e", scores={},
            strategy="s",  # review left NULL — unreviewed evidence still counts
        ))
        session.flush()
        task = InvestigationTask(
            investigation_id=inv_id, task_type="synthesize", objective="synthesize"
        )
        session.add(task)
        session.flush()

        orchestrator.synthesize(session, inv, task)

        assert inv.confidence_breakdown["evidence_count"] == 1
        assert inv.confidence_breakdown["inputs"]["distinct_documents"] == 1

        from argus.investigations.models import Report

        report = session.scalars(
            sa.select(Report).where(Report.investigation_id == inv_id)
        ).one()
        assert f"[chunk:{chunk_kept}]" in report.narrative
        assert f"[chunk:{chunk_rejected}]" not in report.narrative
