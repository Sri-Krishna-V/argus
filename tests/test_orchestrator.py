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
        sa.select(Job).where(Job.job_type == orchestrator.JOB_TYPE, Job.document_id == inv.id)
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
def test_synthesize_scores_sources_and_fuses_context(
    monkeypatch, fake_embeddings, seeded_companies
):
    """PRD-V2 2.3/2.5: synthesize must persist source_rank onto every evidence row
    and emit the fused investigation.context_fused event before drafting."""
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import Evidence, InvestigationEvent
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

    drain_queue()

    with session_scope() as session:
        rows = session.scalars(
            sa.select(Evidence).where(Evidence.investigation_id == inv_id)
        ).all()
        assert rows
        assert all("source_rank" in r.scores for r in rows)
        assert all("source_rank_explanation" in r.scores for r in rows)

        fused = session.scalar(
            sa.select(InvestigationEvent).where(
                InvestigationEvent.investigation_id == inv_id,
                InvestigationEvent.event_type == "investigation.context_fused",
            )
        )
        assert fused is not None
        assert fused.payload["objective"]
        assert fused.payload["evidence"]


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


@requires_db
def test_engine_run_via_dag_and_refresh_marks_obsolete(monkeypatch, fake_embeddings,
                                                       seeded_companies):
    from argus.investigations import engine
    from argus.investigations.models import Investigation, InvestigationTask, Report
    from tests.conftest import drain_queue, ingest_html
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    _register(monkeypatch)
    ingest_html(
        f"<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        f"grew strongly. {FILLER}</p></body></html>", doc_type="news",
    )
    drain_queue()

    with session_scope() as session:
        inv = engine.create(session, "How is the automotive business?")
        inv_id = inv.id
    with session_scope() as session:
        engine.run(session, inv_id)
    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete" and inv.confidence is not None
        v1_tasks = session.scalars(sa.select(InvestigationTask)
                                   .where(InvestigationTask.investigation_id == inv_id)).all()
        assert v1_tasks and all(t.status == "complete" for t in v1_tasks)

    with session_scope() as session:
        engine.refresh(session, inv_id)
    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete" and inv.version == 2
        reports = session.scalars(sa.select(Report)
                                  .where(Report.investigation_id == inv_id)).all()
        assert {r.version for r in reports} == {1, 2}
        tasks = session.scalars(sa.select(InvestigationTask)
                                .where(InvestigationTask.investigation_id == inv_id)).all()
        # v1 tasks stay complete (history preserved); v2 tasks complete too
        assert len(tasks) == 2 * len(v1_tasks)


def test_register_installs_handler(monkeypatch):
    from argus.dataplatform import worker
    from argus.investigations import orchestrator

    monkeypatch.setattr(worker, "EXTRA_HANDLERS", {})
    orchestrator.register()
    orchestrator.register()  # idempotent
    assert worker.EXTRA_HANDLERS[orchestrator.JOB_TYPE] is orchestrator.run_task


@requires_db
def test_compile_dag_dedupes_duplicate_queries(db_session):
    """Two PlannedQuery entries with identical query text must collapse to one
    collect_evidence task (Finding 3): collect_evidence's DELETE-then-reinsert rebuild
    keys on query text, so a duplicate would silently clobber the other's evidence."""
    from argus.investigations import engine, orchestrator

    inv = engine.create(db_session, "q")
    db_session.flush()
    tasks = orchestrator.compile_dag(
        db_session, inv, _plan(queries=("q1", "q1", "q2")), company_ids=[]
    )
    collects = [t for t in tasks if t.task_type == "collect_evidence"]
    assert len(collects) == 2  # not 3 — the duplicate "q1" is dropped, order preserved
    assert [t.inputs["query"] for t in collects] == ["q1", "q2"]


@requires_db
def test_advance_fanin_race_is_serialized(db_session):
    """Finding 1 regression: two collect siblings feeding one synthesize task,
    completed concurrently from two independent DB sessions/threads (ADR-0010 —
    parallelism is multiple worker processes against the same jobs table). Without a
    row lock serializing concurrent _advance calls on the shared pending fan-in node,
    each sibling's plain SELECT can miss the other's just-committed completion and
    neither enqueues synthesize. Follows tests/test_stress.py's real-thread,
    real-session-per-thread convention (not the single-transaction db_session
    fixture, which can't express cross-transaction concurrency)."""
    import threading
    import time as time_mod

    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        session.flush()
        collect1 = InvestigationTask(
            investigation_id=inv_id, task_type="collect_evidence", objective="x",
            status="running",
        )
        collect2 = InvestigationTask(
            investigation_id=inv_id, task_type="collect_evidence", objective="x",
            status="running",
        )
        session.add_all([collect1, collect2])
        session.flush()
        synth = InvestigationTask(
            investigation_id=inv_id, task_type="synthesize", objective="x",
            depends_on=[str(collect1.id), str(collect2.id)],
        )
        session.add(synth)
        session.flush()
        collect1_id, collect2_id, synth_id = collect1.id, collect2.id, synth.id

    a_advanced = threading.Event()
    release = threading.Event()

    def thread_a():
        with session_scope() as s:
            c1 = s.get(InvestigationTask, collect1_id)
            c1.status = "complete"
            orchestrator._advance(s, c1)
            a_advanced.set()
            release.wait(timeout=10)  # hold the fan-in row lock until told to commit

    def thread_b():
        with session_scope() as s:
            c2 = s.get(InvestigationTask, collect2_id)
            c2.status = "complete"
            orchestrator._advance(s, c2)  # blocks here on the row lock, with the fix

    ta = threading.Thread(target=thread_a)
    ta.start()
    assert a_advanced.wait(timeout=5), "thread A never reached _advance"

    tb = threading.Thread(target=thread_b)
    tb.start()

    # Bounded poll: stop as soon as B is observably blocked on a lock, or has
    # already finished (the unfixed-code case: no lock, B races through fast).
    deadline = time_mod.monotonic() + 5
    with session_scope() as poll_session:
        while time_mod.monotonic() < deadline:
            blocked = poll_session.execute(
                sa.text(
                    "select count(*) from pg_stat_activity "
                    "where wait_event_type = 'Lock' and datname = current_database()"
                )
            ).scalar()
            poll_session.rollback()
            if blocked or not tb.is_alive():
                break
            time_mod.sleep(0.05)

    release.set()
    ta.join(timeout=10)
    tb.join(timeout=10)
    assert not ta.is_alive(), "thread A did not finish — deadlock regression"
    assert not tb.is_alive(), "thread B did not finish — deadlock regression"

    with session_scope() as session:
        synth_jobs = [
            j for j in session.scalars(
                sa.select(Job).where(Job.job_type == orchestrator.JOB_TYPE)
            ).all()
            if j.payload.get("task_id") == str(synth_id)
        ]
        assert len(synth_jobs) == 1


@requires_db
def test_drain_returns_when_dependent_stuck_on_failed_task(db_session, monkeypatch):
    """Finding 2 regression: a failed collect_evidence task leaves its dependent
    synthesize task permanently 'pending' (it can never see all deps == 'complete').
    drain()'s only exit condition was 'no pending/running tasks left' — with a stuck
    dependent that never holds, so it must also exit when the investigation itself has
    failed. Includes a second, successfully-completing sibling so the fix can't be
    satisfied by short-circuiting before other legitimate work finishes."""
    import threading

    from argus.investigations import engine, orchestrator
    from argus.investigations.models import Investigation, InvestigationTask

    def flaky_collect(session, inv, task):
        if task.inputs["query"] == "fail":
            raise RuntimeError("boom")
        task.outputs = {"chunk_ids": [], "evidence_count": 0}

    monkeypatch.setitem(orchestrator.HANDLERS, "collect_evidence", flaky_collect)

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        orchestrator.compile_dag(
            session, inv, _plan(queries=("fail", "ok")), company_ids=[]
        )

    result: dict = {}

    def _drain():
        orchestrator.drain(inv_id)
        result["done"] = True

    t = threading.Thread(target=_drain, daemon=True)  # daemon: a regression hangs
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "drain() hung — Finding 2 regression"
    assert result.get("done") is True

    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "failed"
        tasks = session.scalars(
            sa.select(InvestigationTask)
            .where(InvestigationTask.investigation_id == inv_id)
        ).all()
        fail_task = next(t for t in tasks if t.inputs.get("query") == "fail")
        ok_task = next(t for t in tasks if t.inputs.get("query") == "ok")
        synth_task = next(t for t in tasks if t.task_type == "synthesize")
        assert fail_task.status == "failed"
        assert ok_task.status == "complete"  # the sibling's legitimate work finished
        assert synth_task.status == "pending"  # stuck forever — expected, not a bug


@requires_db
def test_replay_matches_per_task(monkeypatch, fake_embeddings, seeded_companies):
    from argus.investigations import engine
    from tests.conftest import drain_queue, ingest_html
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    _register(monkeypatch)
    ingest_html(
        f"<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        f"grew strongly. {FILLER}</p></body></html>", doc_type="news",
    )
    drain_queue()
    with session_scope() as session:
        inv_id = engine.create(session, "How is the automotive business?").id
    with session_scope() as session:
        engine.run(session, inv_id)
    with session_scope() as session:
        result = engine.replay_retrieval(session, inv_id)
        assert result["match"] is True
        assert result["tasks"]  # per-task breakdown


@requires_db
def test_advance_locks_only_dependents_so_siblings_cannot_deadlock(db_session):
    """Two workers completing sibling collect tasks concurrently used to deadlock in
    Postgres: each already holds its own task's row (run_task's `status = "running"`
    flip is autoflushed) while the other transaction still sees that row as pending,
    so a `FOR UPDATE` over *every* pending row made A wait on B's row and B on A's.
    Postgres killed one, its job died at max_attempts=1, and drain() was left spinning
    on a DAG that could never finish — observed in production while seeding the demo
    set. Locking only the rows that depend on the completed task removes the cycle.

    Note the sibling rows must be committed as `pending` here: the pre-existing
    fan-in test commits them as `running`, which keeps them out of the locked set and
    is why it never caught this."""
    import threading

    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        session.flush()
        collects = [
            InvestigationTask(
                investigation_id=inv_id, task_type="collect_evidence", objective="x"
            )
            for _ in range(2)
        ]
        session.add_all(collects)
        session.flush()
        collect_ids = [c.id for c in collects]
        session.add(
            InvestigationTask(
                investigation_id=inv_id, task_type="synthesize", objective="x",
                depends_on=[str(c) for c in collect_ids],
            )
        )

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def complete(task_id):
        try:
            with session_scope() as s:
                task = s.get(InvestigationTask, task_id)
                task.status = "complete"
                s.flush()  # takes this row's lock, exactly as run_task does
                barrier.wait(timeout=15)
                orchestrator._advance(s, task)
        except Exception as exc:  # noqa: BLE001 - the deadlock victim lands here
            errors.append(exc)

    threads = [threading.Thread(target=complete, args=(tid,)) for tid in collect_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()

    assert not errors, f"sibling completions deadlocked: {errors}"
    with session_scope() as session:
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(Job)
            .where(Job.job_type == orchestrator.JOB_TYPE, Job.document_id == inv_id)
        ), "synthesize was never enqueued"


@requires_db
def test_drain_returns_when_a_task_job_is_dead(db_session):
    """A dead investigation.task job leaves its task row pending with nothing left to
    claim, so drain()'s pending-tasks exit condition never holds and it spun forever —
    hanging whatever called it (a POST /api/investigations request, the demo seeder).
    It must return instead and let _finalize fail the investigation."""
    import threading

    from argus.core.models import Job
    from argus.investigations import engine, orchestrator

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        orchestrator.compile_dag(session, inv, _plan(), company_ids=[])

    with session_scope() as session:
        session.execute(
            sa.update(Job)
            .where(Job.job_type == orchestrator.JOB_TYPE, Job.document_id == inv_id)
            .values(status="dead", attempts=1, last_error="OperationalError: deadlock")
        )

    t = threading.Thread(target=orchestrator.drain, args=(inv_id,), daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "drain() hung on a dead task job"
