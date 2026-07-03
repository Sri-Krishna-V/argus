import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from argus.core.config import get_settings


def _db_available() -> bool:
    try:
        engine = sa.create_engine(
            get_settings().database_url, connect_args={"connect_timeout": 2}
        )
        with engine.connect():
            return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()

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
