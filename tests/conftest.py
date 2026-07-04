import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from argus.core.config import get_settings


def _ensure_test_db() -> bool:
    """Point the whole process at an isolated argus_test database, creating it if
    needed. Tests wipe schemas (migration round-trip) — they must never touch dev data."""
    base_url = sa.engine.make_url(get_settings().database_url)
    if base_url.database == "argus_test":
        return True
    try:
        admin = sa.create_engine(
            base_url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            connect_args={"connect_timeout": 2},
        )
        with admin.connect() as conn:
            exists = conn.execute(
                sa.text("select 1 from pg_database where datname = 'argus_test'")
            ).scalar()
            if not exists:
                conn.execute(sa.text("create database argus_test"))
    except Exception:
        return False

    os.environ["ARGUS_DATABASE_URL"] = base_url.set(database="argus_test").render_as_string(
        hide_password=False
    )
    get_settings.cache_clear()
    import argus.core.db as db

    db._engine = None
    db._session_factory = None
    return True


DB_AVAILABLE = _ensure_test_db()

requires_db = pytest.mark.skipif(not DB_AVAILABLE, reason="Postgres not running (make up)")


@pytest.fixture(scope="session")
def migrated_db():
    """Upgrade to head once per test session; tests own their data."""
    command.upgrade(Config("alembic.ini"), "head")
    from argus.core.db import get_engine

    return get_engine()


@pytest.fixture
def db_session(migrated_db):
    from argus.core.db import session_scope

    with session_scope() as session:
        yield session
        session.rollback()


@pytest.fixture
def fake_embeddings(monkeypatch):
    from argus.dataplatform import embeddings

    monkeypatch.setattr(embeddings, "_provider", embeddings.FakeProvider())


@pytest.fixture
def seeded_companies(db_session):
    """Canonical test companies. Fake tickers: real ones would land on the SEC watchlist."""
    from argus.dataplatform import pipeline
    from argus.knowledge.models import Company

    ids = {}
    for name, cik, tickers, aliases in [
        ("NVIDIA CORP", "9990001", ["ZZZT"], ["NVIDIA"]),
        ("Apple Inc.", "9990002", ["ZZAP"], ["Apple"]),
    ]:
        company = db_session.scalar(sa.select(Company).where(Company.cik == cik))
        if company is None:
            company = Company(name=name, cik=cik, tickers=tickers, aliases=aliases)
            db_session.add(company)
            db_session.flush()
        ids[name] = company.id
    db_session.commit()
    pipeline._matcher = None  # matcher caches the canonical table per process
    return ids


class StubConnector:
    name = "test_stub"

    def __init__(self, html: str, native_id: str):
        self.html, self.native_id = html, native_id

    def discover(self):
        from argus.dataplatform.connectors.base import DocumentRef

        return [
            DocumentRef(
                source="test_stub",
                native_id=self.native_id,
                doc_type="news",
                title="stub document",
                url="https://example.com/stub",
                inline_content=self.html.encode(),
            )
        ]


def ingest_html(html: str):
    """Ingest one stub document; returns its document id."""
    import uuid

    from argus.core.db import session_scope
    from argus.dataplatform.connectors.base import ingest
    from argus.knowledge.models import Document

    native_id = str(uuid.uuid4())
    with session_scope() as session:
        assert ingest(session, StubConnector(html, native_id))["new"] == 1
        return session.scalar(
            sa.select(Document.id).where(Document.source_native_id == native_id)
        )


def drain_queue(limit: int = 200) -> int:
    from argus.dataplatform.worker import run_once

    ran = 0
    while run_once():
        ran += 1
        assert ran < limit, "queue did not drain"
    return ran
