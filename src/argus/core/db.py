from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from argus.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all Argus models."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={
                "options": f"-c statement_timeout={settings.db_statement_timeout_ms}"
            },
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional unit of work: commits on success, rolls back on error."""
    get_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
