"""Phase 10 enterprise-default features: opt-in API-key auth, request-ID
correlation, the readiness probe, and pagination bounds on list endpoints.
Phase 11 hardening: security headers, body-size cap, per-IP rate limiting,
input length caps, and the citation URL scheme guard."""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations.models import Investigation, InvestigationLink, Report
from argus.knowledge.models import Chunk
from argus.main import _buckets, app
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]

FILLER = "Quarterly commentary follows. " + "filler " * 40


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def with_api_key(monkeypatch):
    """Turn auth on for one test; restores the (empty, disabled) default after."""
    monkeypatch.setenv("ARGUS_API_KEY", "test-secret-key")
    get_settings.cache_clear()
    yield "test-secret-key"
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rate_limit_bucket():
    """The token bucket is a module-level dict keyed by client IP; every test in
    this module hits the app as the same TestClient host, so it must be cleared
    around each test or unrelated tests would starve each other's quota."""
    _buckets.clear()
    yield
    _buckets.clear()


@pytest.fixture
def rate_limit_of(monkeypatch):
    """Override the per-minute investigation rate limit for one test."""

    def _set(n: int):
        monkeypatch.setenv("ARGUS_RATE_LIMIT_INVESTIGATIONS_PER_MINUTE", str(n))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


# --- auth off (default) ---


def test_auth_off_by_default_api_works_without_a_key(client):
    assert get_settings().api_key == ""
    assert client.get("/api/companies", params={"q": "NVIDIA"}).status_code == 200


# --- auth on ---


def test_auth_on_missing_key_is_401(client, with_api_key):
    r = client.get("/api/companies", params={"q": "NVIDIA"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or missing API key"}


def test_auth_on_wrong_key_is_401(client, with_api_key):
    r = client.get("/api/companies", params={"q": "NVIDIA"}, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_auth_on_correct_x_api_key_is_200(client, with_api_key):
    r = client.get(
        "/api/companies", params={"q": "NVIDIA"}, headers={"X-API-Key": with_api_key}
    )
    assert r.status_code == 200


def test_auth_on_correct_bearer_token_is_200(client, with_api_key):
    r = client.get(
        "/api/companies",
        params={"q": "NVIDIA"},
        headers={"Authorization": f"Bearer {with_api_key}"},
    )
    assert r.status_code == 200


def test_auth_on_health_and_ui_stay_open(client, with_api_key):
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/").status_code == 200


# --- request-id correlation ---


def test_response_carries_a_request_id(client):
    r = client.get("/health")
    assert r.headers["X-Request-ID"]


def test_provided_request_id_is_echoed_back(client):
    r = client.get("/health", headers={"X-Request-ID": "caller-supplied-id"})
    assert r.headers["X-Request-ID"] == "caller-supplied-id"


# --- readiness ---


def test_readiness_probe_ok(client):
    assert client.get("/health/ready").json() == {"status": "ready"}


# --- pagination ---


_docs: list | None = None


@pytest.fixture
def companies_and_investigations(client, monkeypatch):
    """A handful of investigations to paginate over, created once per module. Uses
    the fake adapter so creation never makes a live LLM call — whether the run
    itself finds evidence is irrelevant here, only that the row gets created."""
    global _docs
    if _docs is None:
        from tests.test_investigations import _fake_adapter

        _fake_adapter(monkeypatch)
        for i in range(3):
            r = client.post("/api/investigations", json={"question": f"pagination check {i}"})
            assert r.status_code == 201
        _docs = True
    return _docs


def test_investigations_pagination_limit_and_offset(client, companies_and_investigations):
    page1 = client.get("/api/investigations", params={"limit": 1, "offset": 0}).json()
    page2 = client.get("/api/investigations", params={"limit": 1, "offset": 1}).json()
    assert len(page1) == 1
    assert len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]


def test_investigations_limit_out_of_range_is_422(client):
    assert client.get("/api/investigations", params={"limit": 0}).status_code == 422
    assert client.get("/api/investigations", params={"limit": 999}).status_code == 422


def test_companies_limit_out_of_range_is_422(client):
    assert client.get("/api/companies", params={"q": "x", "limit": 0}).status_code == 422
    assert client.get("/api/companies", params={"q": "x", "limit": 500}).status_code == 422


def test_search_k_out_of_range_is_422(client):
    assert client.get("/api/search", params={"q": "x", "k": 0}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "k": -1}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "k": 101}).status_code == 422


def test_evidence_limit_and_offset(client, monkeypatch):
    from tests.test_investigations import _fake_adapter

    ingest_html(
        f"<html><body><p>NVIDIA CORP evidence pagination seed document about "
        f"automotive self-driving platform revenue. {FILLER}</p></body></html>",
        published_at=datetime(2026, 6, 1, tzinfo=UTC), doc_type="news",
    )
    drain_queue()
    _fake_adapter(monkeypatch)
    created = client.post(
        "/api/investigations", json={"question": "How is the DC business?"}
    ).json()
    inv_id = created["id"]

    full = client.get(f"/api/investigations/{inv_id}/evidence").json()
    limited = client.get(
        f"/api/investigations/{inv_id}/evidence", params={"limit": 1, "offset": 0}
    ).json()
    assert len(limited) == min(1, len(full))
    if len(full) > 1:
        second = client.get(
            f"/api/investigations/{inv_id}/evidence", params={"limit": 1, "offset": 1}
        ).json()
        assert second[0]["chunk_id"] != limited[0]["chunk_id"]


def _dead_job(**overrides) -> int:
    with session_scope() as session:
        job = Job(job_type="parse", status="dead", attempts=3, last_error="boom", **overrides)
        session.add(job)
        session.flush()
        return job.id


def test_list_jobs_filters_by_status(client):
    dead_id = _dead_job()
    jobs = client.get("/api/jobs", params={"status": "dead"}).json()
    assert any(j["id"] == dead_id and j["last_error"] == "boom" for j in jobs)


def test_list_jobs_unknown_status_is_422(client):
    assert client.get("/api/jobs", params={"status": "bogus"}).status_code == 422


def test_retry_job_resets_dead_job_to_pending(client):
    job_id = _dead_job()
    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200
    assert r.json() == {"retried": True}
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job.status == "pending"
        assert job.attempts == 0


def test_retry_job_unknown_id_is_404(client):
    assert client.post("/api/jobs/999999999/retry").status_code == 404


def test_retry_job_not_dead_is_404(client):
    with session_scope() as session:
        job = Job(job_type="parse", status="pending")
        session.add(job)
        session.flush()
        job_id = job.id
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 404


def test_pipeline_metrics_includes_document_count(client, seeded_companies):
    body = client.get("/api/metrics/pipeline").json()
    assert body["document_count"] >= 0


# --- security headers ---


def _assert_security_headers(headers):
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert "default-src 'self'" in headers["Content-Security-Policy"]


def test_security_headers_on_200(client):
    _assert_security_headers(client.get("/health").headers)


def test_security_headers_on_401(client, with_api_key):
    r = client.get("/api/companies", params={"q": "NVIDIA"})
    assert r.status_code == 401
    _assert_security_headers(r.headers)


def test_security_headers_on_404(client):
    r = client.get(f"/api/documents/{uuid.uuid4()}")
    assert r.status_code == 404
    _assert_security_headers(r.headers)


# --- body size cap ---


def test_body_over_cap_is_413(client):
    cap = get_settings().max_body_bytes
    r = client.post(
        "/api/investigations",
        content=b"x" * (cap + 1),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413


def test_body_just_under_cap_is_not_413(client):
    cap = get_settings().max_body_bytes
    body = ('{"question": "' + "x" * (cap - 100) + '"}').encode()
    assert len(body) < cap
    r = client.post(
        "/api/investigations", content=body, headers={"Content-Type": "application/json"}
    )
    # too far past the 2000-char question cap to succeed, but it must fail on
    # validation (422), never on the body-size gate (413)
    assert r.status_code != 413


# --- rate limiting ---


def test_rate_limit_429_after_bucket_exhausted(client, monkeypatch, rate_limit_of):
    from tests.test_investigations import _fake_adapter

    rate_limit_of(2)
    _fake_adapter(monkeypatch)
    for _ in range(2):
        r = client.post("/api/investigations", json={"question": "rate limit check"})
        assert r.status_code == 201
    r = client.post("/api/investigations", json={"question": "rate limit check"})
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"]


def test_rate_limit_disabled_when_zero(client, monkeypatch, rate_limit_of):
    from tests.test_investigations import _fake_adapter

    rate_limit_of(0)
    _fake_adapter(monkeypatch)
    for _ in range(5):
        r = client.post("/api/investigations", json={"question": "no limit check"})
        assert r.status_code == 201


# --- input length caps ---


def test_search_q_over_500_chars_is_422(client):
    assert client.get("/api/search", params={"q": "x" * 501}).status_code == 422


def test_companies_q_over_500_chars_is_422(client):
    assert client.get("/api/companies", params={"q": "x" * 501}).status_code == 422


def test_create_investigation_question_over_2000_chars_is_422(client):
    r = client.post("/api/investigations", json={"question": "x" * 2001})
    assert r.status_code == 422


def test_create_investigation_empty_question_is_422(client):
    r = client.post("/api/investigations", json={"question": ""})
    assert r.status_code == 422


# --- vendored static assets ---


def test_static_htmx_is_served(client):
    r = client.get("/static/htmx.min.js")
    assert r.status_code == 200


# --- citation URL scheme guard ---


def _investigation_citing(url: str) -> uuid.UUID:
    """Minimal investigation + report citing one real chunk, bypassing the agent
    pipeline entirely — only the view's citation-rendering path is under test."""
    doc_id = ingest_html(
        "<html><body><p>Citation guard fixture document about a topic.</p></body></html>",
        url=url, doc_type="news",
    )
    drain_queue()
    with session_scope() as session:
        chunk_id = session.scalar(
            sa.select(Chunk.id).where(Chunk.document_id == doc_id).limit(1)
        )
        inv = Investigation(question="citation guard check")
        session.add(inv)
        session.flush()
        session.add(Report(
            investigation_id=inv.id, executive_summary="s",
            narrative=f"See the source [chunk:{chunk_id}].", model="test",
        ))
        return inv.id


def test_citation_javascript_url_is_not_rendered_as_a_link(client):
    inv_id = _investigation_citing("javascript:alert(1)")
    r = client.get(f"/investigations/{inv_id}")
    assert r.status_code == 200
    assert "javascript:" not in r.text


def test_citation_http_url_still_renders_as_a_link(client):
    inv_id = _investigation_citing("https://example.com/good-source")
    r = client.get(f"/investigations/{inv_id}")
    assert r.status_code == 200
    assert 'href="https://example.com/good-source"' in r.text


# --- report endpoint: numbered, guarded citations ---


def test_report_citation_javascript_url_is_nulled(client):
    inv_id = _investigation_citing("javascript:alert(1)")
    r = client.get(f"/api/investigations/{inv_id}/report")
    assert r.status_code == 200
    citations = r.json()["citations"]
    assert citations[0]["url"] is None
    assert citations[0]["index"] == 1


def test_report_citation_http_url_is_kept(client):
    inv_id = _investigation_citing("https://example.com/good-source")
    r = client.get(f"/api/investigations/{inv_id}/report")
    assert r.status_code == 200
    citations = r.json()["citations"]
    assert citations[0]["url"] == "https://example.com/good-source"


def test_report_with_no_citations_returns_empty_list(client):
    # ponytail: bypass the agent pipeline (its citation gate rejects marker-less
    # drafts — ADR-0005) and insert a marker-less report directly, same pattern
    # as _investigation_citing. Deterministic: no dependency on shared-DB search state.
    with session_scope() as session:
        inv = Investigation(question="no citations in this narrative")
        session.add(inv)
        session.flush()
        session.add(Report(
            investigation_id=inv.id, executive_summary="s",
            narrative="Growth is strong, no citations needed.", model="test",
        ))
        inv_id = inv.id
    r = client.get(f"/api/investigations/{inv_id}/report")
    assert r.status_code == 200
    assert r.json()["citations"] == []


# --- investigation detail: hypotheses and links ---


def test_investigation_detail_includes_hypotheses_and_links(client):
    from argus.investigations import engine

    with session_scope() as session:
        inv = engine.create(session, "does X affect Y?", "yes, because Z")
        other = Investigation(question="a related question")
        session.add(other)
        session.flush()
        session.add(InvestigationLink(
            src_investigation_id=inv.id, dst_investigation_id=other.id,
            link_type="relates_to",
        ))
        inv_id = inv.id

    r = client.get(f"/api/investigations/{inv_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["hypotheses"][0]["statement"] == "yes, because Z"
    assert body["links"][0]["link_type"] == "relates_to"
    assert body["links"][0]["question"] == "a related question"


def test_investigation_detail_with_no_hypotheses_or_links_returns_empty_lists(client):
    with session_scope() as session:
        inv = Investigation(question="standalone question")
        session.add(inv)
        session.flush()
        inv_id = inv.id

    body = client.get(f"/api/investigations/{inv_id}").json()
    assert body["hypotheses"] == []
    assert body["links"] == []


@requires_db
def test_tasks_endpoint_lists_dag(monkeypatch, fake_embeddings, seeded_companies):
    from fastapi.testclient import TestClient

    from argus.dataplatform import worker
    from argus.investigations import engine, orchestrator
    from argus.main import app as fastapi_app
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    monkeypatch.setitem(worker.EXTRA_HANDLERS, orchestrator.JOB_TYPE, orchestrator.run_task)
    ingest_html(
        "<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        "grew.</p></body></html>", doc_type="news",
    )
    drain_queue()
    with session_scope() as session:
        inv_id = engine.create(session, "How is the automotive business?").id
    engine.execute(inv_id, "run")

    client = TestClient(fastapi_app)
    r = client.get(f"/api/investigations/{inv_id}/tasks")
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    assert {t["task_type"] for t in tasks} == {"collect_evidence", "synthesize"}
    assert all(t["status"] == "complete" for t in tasks)
    synth = next(t for t in tasks if t["task_type"] == "synthesize")
    assert synth["depends_on"]


@requires_db
def test_tasks_endpoint_404s_on_unknown_investigation(fake_embeddings):
    import uuid as _uuid

    from fastapi.testclient import TestClient

    from argus.main import app as fastapi_app

    client = TestClient(fastapi_app)
    assert client.get(f"/api/investigations/{_uuid.uuid4()}/tasks").status_code == 404
