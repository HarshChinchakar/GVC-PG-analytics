"""Engine and session management.

The rest of the application only ever asks for a Session; it never learns which
database is behind it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _build_engine() -> Engine:
    kwargs: dict = {"echo": settings.database_echo, "future": True}

    if settings.is_sqlite:
        # check_same_thread=False is required because FastAPI serves requests
        # from a thread pool. Safety still comes from one Session per request.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Supabase's pooler already pools connections, so keep our own pool
        # small. pool_pre_ping avoids handing out connections the pooler has
        # already reaped, which is the usual cause of stale-connection errors
        # on free tiers that idle down.
        kwargs.update(pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=1800)

        # Supabase's port-6543 endpoint is PgBouncer in TRANSACTION mode, which
        # does not support server-side prepared statements: a connection can be
        # handed to a different client between statements, so a prepared plan
        # named on one may not exist on the next. psycopg3 prepares
        # automatically after a few executions, which surfaces later as
        # intermittent "prepared statement does not exist" errors under load.
        # Disabling preparation entirely is the supported fix.
        if ":6543" in settings.database_url:
            kwargs["connect_args"] = {"prepare_threshold": None}

    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record) -> None:
    """Make SQLite behave like the Postgres we are heading towards.

    Without `foreign_keys=ON` SQLite silently ignores every FK constraint we
    declare, which would let development data drift into states Postgres will
    later reject. WAL and a busy timeout keep concurrent reads from tripping
    over writes during seeding and local testing.
    """
    if not settings.is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background jobs."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
