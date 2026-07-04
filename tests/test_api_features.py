"""Phase 10 enterprise-default features: opt-in API-key auth, request-ID
correlation, the readiness probe, and pagination bounds on list endpoints."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from argus.core.config import get_settings
from argus.main import app
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
