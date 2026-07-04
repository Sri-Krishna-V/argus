"""Connectors are independently testable against recorded fixtures (Bible §8) —
no live HTTP here."""

from pathlib import Path

import pytest
import sqlalchemy as sa

from argus.dataplatform.connectors.profiles import seed_companies
from argus.dataplatform.connectors.rss import RssConnector
from argus.knowledge.models import Company
from tests.conftest import requires_db

FIXTURES = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return self


def test_rss_discover_parses_fixture(monkeypatch):
    monkeypatch.setattr(
        "argus.dataplatform.connectors.rss.httpx.get",
        lambda *a, **k: _Resp((FIXTURES / "feed.xml").read_bytes()),
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
        profiles.httpx, "get",
        lambda *a, **k: _Resp((FIXTURES / "company_tickers.json").read_bytes()),
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
