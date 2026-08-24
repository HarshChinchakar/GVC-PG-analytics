"""Declarative base and shared model mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.types import GUID, TZDateTime, new_uuid, utcnow

# Explicit constraint naming. Without this SQLite invents anonymous constraint
# names, which makes later Alembic migrations against Postgres unable to drop or
# alter them by name. Setting it up front costs nothing and avoids a painful
# migration later.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """UUID primary keys.

    Chosen over autoincrement integers because ids are generated client-side
    (no round trip), they do not leak business volume when they appear in URLs,
    and they merge cleanly if data from several sources is ever combined.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=new_uuid
    )


class TimestampMixin:
    """Created/updated bookkeeping, defaulted in Python for cross-backend
    consistency (SQLite and Postgres disagree on server-side now())."""

    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )


class LocationScopedMixin:
    """Stamps a row with its owning location.

    Every operational table carries `location_id` directly, even where it could
    be reached by joining through a parent. This is deliberate: it lets every
    query filter isolation in one predicate, it makes the tenant boundary
    impossible to forget, and it is exactly the column a Supabase Row Level
    Security policy will need once we move to Postgres.
    """

    @property
    def _location_fk(self):  # pragma: no cover - documentation helper
        raise NotImplementedError


def location_fk(*, index: bool = True) -> Mapped[uuid.UUID]:
    """Standard non-null FK to locations.id with an index."""
    return mapped_column(
        GUID(),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=index,
    )
