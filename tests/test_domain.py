"""Phase 2 invariants: immutability, append-only events, canonical uniqueness,
migration round-trip. Requires Postgres (make up)."""

import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from argus.knowledge.models import Company, Document
from argus.knowledge.repositories import CompanyRepository, DocumentRepository
from tests.conftest import requires_db

pytestmark = requires_db


def _doc(**overrides) -> Document:
    defaults = dict(
        source="test",
        source_native_id=str(uuid.uuid4()),
        checksum=str(uuid.uuid4()),
        raw_path="data/raw/test",
        doc_type="news",
    )
    return Document(**{**defaults, **overrides})


def test_document_content_is_immutable(db_session):
    doc = DocumentRepository(db_session).add(_doc(title="original"))
    db_session.commit()

    doc.title = "tampered"
    with pytest.raises(sa.exc.DBAPIError, match="immutable"):
        db_session.flush()


def test_document_status_may_advance(db_session):
    repo = DocumentRepository(db_session)
    doc = repo.add(_doc())
    repo.advance_status(doc.id, "parsed")
    assert repo.get(doc.id).status == "parsed"


def test_events_are_append_only(db_session):
    db_session.execute(sa.text("INSERT INTO events (event_type) VALUES ('test.event')"))
    with pytest.raises(sa.exc.DBAPIError, match="append-only"):
        db_session.execute(sa.text("UPDATE events SET event_type = 'x'"))
    db_session.rollback()
    db_session.execute(sa.text("INSERT INTO events (event_type) VALUES ('test.event')"))
    with pytest.raises(sa.exc.DBAPIError, match="append-only"):
        db_session.execute(sa.text("DELETE FROM events"))
    db_session.rollback()


def test_company_cik_is_canonical(db_session):
    cik = str(uuid.uuid4())[:10]
    repo = CompanyRepository(db_session)
    repo.add(Company(name="NVIDIA Corp", cik=cik))
    with pytest.raises(sa.exc.IntegrityError):
        repo.add(Company(name="NVIDIA Corporation", cik=cik))


def test_document_source_native_id_dedupes(db_session):
    repo = DocumentRepository(db_session)
    native = str(uuid.uuid4())
    repo.add(_doc(source_native_id=native))
    with pytest.raises(sa.exc.IntegrityError):
        repo.add(_doc(source_native_id=native))


def test_migration_round_trip(migrated_db):
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with migrated_db.connect() as conn:
        tables = set(sa.inspect(conn).get_table_names())
    assert {"documents", "companies", "chunks", "events", "jobs", "graph_edges"} <= tables
