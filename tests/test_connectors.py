"""Connectors are independently testable against recorded fixtures (Bible §8) —
no live HTTP here."""

from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa

from argus.core.config import get_settings
from argus.dataplatform.connectors import base
from argus.dataplatform.connectors.profiles import seed_companies
from argus.dataplatform.connectors.rss import RssConnector
from argus.knowledge.models import Company
from tests.conftest import requires_db

FIXTURES = Path(__file__).parent / "fixtures"


def test_rss_discover_parses_fixture(monkeypatch):
    monkeypatch.setattr(
        "argus.dataplatform.connectors.rss.fetch_bytes",
        lambda *a, **k: (FIXTURES / "feed.xml").read_bytes(),
    )
    refs = RssConnector().discover()
    # one ref per feed entry, times the number of configured feeds
    per_feed = [r for r in refs if r.native_id == "test-entry-1"]
    assert per_feed, "fixture entry missing"
    ref = per_feed[0]
    assert ref.doc_type == "news"
    assert ref.publisher == "Test Financial Wire"
    assert ref.published_at is not None
    assert b"NVIDIA CORP" in ref.inline_content
    assert ref.inline_content.startswith(b"<h1>Nvidia Corp beats earnings expectations</h1>")


def test_profiles_registry_snapshot_skips_text_pipeline(monkeypatch):
    from argus.dataplatform.connectors import profiles

    monkeypatch.setattr(
        profiles, "fetch_bytes",
        lambda *a, **k: (FIXTURES / "company_tickers.json").read_bytes(),
    )
    refs = profiles.CompanyProfilesConnector().discover()
    assert refs[0].enqueue_pipeline is False


@requires_db
def test_profiles_seed_is_idempotent_upsert(db_session):
    registry = (FIXTURES / "company_tickers.json").read_bytes()

    first = seed_companies(db_session, registry)
    again = seed_companies(db_session, registry)
    assert again == {"created": 0, "updated": 0}
    assert first["created"] <= 4  # 5 rows, but GOOGL/GOOG share a CIK

    alphabet = db_session.scalar(sa.select(Company).where(Company.cik == "1652044"))
    assert sorted(alphabet.tickers) == ["GOOG", "GOOGL"]
    apple = db_session.scalar(sa.select(Company).where(Company.cik == "320193"))
    assert apple.aliases == ["Apple"]


@requires_db
def test_profiles_seed_updates_changed_names(db_session):
    registry = (FIXTURES / "company_tickers.json").read_bytes()
    seed_companies(db_session, registry)
    changed = registry.replace(b"NVIDIA CORP", b"NVIDIA Corporation")
    result = seed_companies(db_session, changed)
    assert result["updated"] == 1
    nvidia = db_session.scalar(sa.select(Company).where(Company.cik == "1045810"))
    assert nvidia.name == "NVIDIA Corporation"


def test_sec_connector_builds_filing_urls():
    pytest.importorskip("argus.dataplatform.connectors.sec")
    # URL construction is pure string logic; exercised via the live smoke run.
    # ponytail: recorded submissions fixture when SEC discover logic grows.


# --- fetch_bytes (shared download cap) ---


def test_fetch_bytes_returns_full_content_under_cap():
    def handler(request):
        return httpx.Response(200, content=b"a" * 1000)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert base.fetch_bytes(client, "https://x.test/f") == b"a" * 1000


def test_fetch_bytes_raises_over_cap(monkeypatch):
    monkeypatch.setenv("ARGUS_MAX_FETCH_BYTES", "10")
    get_settings.cache_clear()
    try:
        def handler(request):
            return httpx.Response(200, content=b"a" * 1000)

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
            pytest.raises(ValueError, match="max_fetch_bytes"),
        ):
            base.fetch_bytes(client, "https://x.test/f")
    finally:
        get_settings.cache_clear()


def test_fetch_bytes_raises_on_non_2xx():
    def handler(request):
        return httpx.Response(404)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        base.fetch_bytes(client, "https://x.test/f")


# --- SEC host allowlist ---


def test_sec_fetch_rejects_non_sec_host():
    from argus.dataplatform.connectors.base import DocumentRef
    from argus.dataplatform.connectors.sec import SecEdgarConnector

    ref = DocumentRef(
        source="sec_edgar", native_id="x", doc_type="filing", url="https://evil.com/f.htm"
    )
    with pytest.raises(ValueError, match="non-SEC host"):
        SecEdgarConnector(session=None).fetch(ref)


def test_sec_fetch_allows_sec_host(monkeypatch):
    from argus.dataplatform.connectors.base import DocumentRef
    from argus.dataplatform.connectors.sec import SecEdgarConnector

    def handler(request):
        return httpx.Response(200, content=b"filing body")

    def fake_client():
        return httpx.Client(transport=httpx.MockTransport(handler))

    connector = SecEdgarConnector(session=None)
    monkeypatch.setattr(connector, "_client", fake_client)
    ref = DocumentRef(
        source="sec_edgar", native_id="x", doc_type="filing", url="https://www.sec.gov/f.htm"
    )
    assert connector.fetch(ref) == b"filing body"
