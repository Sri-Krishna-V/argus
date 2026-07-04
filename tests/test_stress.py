import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from argus.core import events
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.models import Job
from argus.dataplatform import worker
from argus.research.retrieval import search
from tests.conftest import drain_queue, ingest_html, requires_db

log = logging.getLogger(__name__)


@requires_db
def test_queue_under_load(db_session, fake_embeddings):
    doc_id = ingest_html("<html><body><p>stress load seed document.</p></body></html>")
    drain_queue()  # get the doc past the pipeline once, so re-validating is cheap

    with session_scope() as session:
        for _ in range(300):
            events.enqueue(session, "validate", document_id=doc_id)

    started = time.monotonic()
    ran = drain_queue(limit=1000)
    elapsed = time.monotonic() - started
    log.info(
        "queue under load", extra={"context": {"jobs": ran, "elapsed_s": elapsed,
                                                "jobs_per_sec": ran / max(elapsed, 1e-6)}},
    )
    assert ran == 300
    with session_scope() as session:
        leftover = session.scalar(
            sa.select(sa.func.count()).select_from(Job)
            .where(Job.status.in_(["running", "pending"]), Job.document_id == doc_id)
        )
        assert leftover == 0


@requires_db
def test_concurrent_claim_safety(db_session, fake_embeddings):
    doc_id = ingest_html("<html><body><p>concurrent claim seed document.</p></body></html>")
    drain_queue()
    with session_scope() as session:
        for _ in range(60):
            events.enqueue(session, "validate", document_id=doc_id)

    executed: list[int] = []
    lock = threading.Lock()

    def worker_loop():
        while True:
            with session_scope() as session:
                job = worker.claim_next(session)
                if job is None:
                    return
                job_id = job.id
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
            with lock:
                executed.append(job_id)

    threads = [threading.Thread(target=worker_loop) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(executed) == 60
    assert len(set(executed)) == 60


@requires_db
def test_reaper_under_contention(db_session, fake_embeddings):
    doc_id = ingest_html("<html><body><p>reaper contention seed document.</p></body></html>")
    drain_queue()
    lease = get_settings().job_lease_seconds

    with session_scope() as session:
        for _ in range(20):
            events.enqueue(session, "validate", document_id=doc_id)
        for _ in range(20):
            job = Job(
                job_type="validate", document_id=doc_id, status="running",
                claimed_at=datetime.now(UTC) - timedelta(seconds=lease + 60),
            )
            session.add(job)

    executed: list[int] = []
    lock = threading.Lock()
    stop = threading.Event()

    def claimer_loop():
        misses = 0
        while misses < 50:
            with lock:
                if len(executed) >= 40:
                    return
            with session_scope() as session:
                job = worker.claim_next(session)
                if job is None:
                    misses += 1
                    time.sleep(0.02)
                    continue
                misses = 0
                job_id = job.id
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
            with lock:
                executed.append(job_id)

    def reaper_loop():
        while not stop.is_set():
            with session_scope() as session:
                worker.reap_stale(session)
            time.sleep(0.01)

    reaper_thread = threading.Thread(target=reaper_loop)
    reaper_thread.start()
    claimers = [threading.Thread(target=claimer_loop) for _ in range(4)]
    for t in claimers:
        t.start()
    for t in claimers:
        t.join()
    stop.set()
    reaper_thread.join()

    assert len(executed) == 40
    assert len(set(executed)) == 40


@requires_db
def test_retrieval_boundary_inputs(db_session, fake_embeddings):
    ingest_html("<html><body><p>boundary retrieval seed document.</p></body></html>")
    drain_queue()

    queries = [
        ("", 10), ("   ", 10), ("x" * 10_000, 10),
        ("苹果公司 📉 risque", 10), ("'; DROP TABLE documents;--", 10),
        ("normal query", 1), ("normal query", 0), ("normal query", 500),
    ]
    for q, k in queries:
        results = search(db_session, q, k=k)
        assert isinstance(results, list)

    assert db_session.execute(sa.text("select 1 from documents limit 1")).first() is not None


@requires_db
def test_large_golden_set_eval(db_session, seeded_companies, fake_embeddings):
    from argus.evals.runner import eval_retrieval

    ingest_html(
        "<html><body><p>ZZZT NVIDIA CORP earnings report golden set stress test.</p></body></html>",
        doc_type="news",
    )
    drain_queue()

    questions = []
    for i in range(200):
        ticker = "ZZZT" if i % 4 == 0 else f"NOPE{i}"
        questions.append({
            "id": f"q{i}",
            "question": "how did the company perform",
            "expected": [{"ticker": ticker}],
        })
    golden = {"version": "stress/v1", "questions": questions}

    metrics = eval_retrieval(db_session, golden, k=5)
    resolvable = sum(1 for i in range(200) if i % 4 == 0)
    assert metrics["skipped"] == 200 - resolvable
    assert len(metrics["per_question"]) + metrics["skipped"] == 200


@requires_db
def test_api_garbage_inputs(fake_embeddings):
    from fastapi.testclient import TestClient

    from argus.main import app as fastapi_app

    client = TestClient(fastapi_app)

    r = client.get("/api/investigations/not-a-uuid")
    assert r.status_code == 422

    r = client.get(f"/api/documents/{uuid.uuid4()}")
    assert r.status_code == 404

    # k is bounded (ge=1, le=100) at the API layer: out-of-range is a 422, not a 500
    r = client.get("/api/search", params={"q": "", "k": -1})
    assert r.status_code == 422

    r = client.get("/api/search", params={"q": "anything", "k": 0})
    assert r.status_code == 422

    r = client.get("/api/search", params={"q": "x" * 5000, "k": 500})
    assert r.status_code == 422


@requires_db
def test_api_large_question_investigation(monkeypatch, fake_embeddings):
    from fastapi.testclient import TestClient

    from argus.main import app as fastapi_app
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    client = TestClient(fastapi_app)
    r = client.post("/api/investigations", json={"question": "why? " * 20_000})
    assert r.status_code in (201, 422)
