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
