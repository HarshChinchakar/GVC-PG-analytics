"""Portable column types.

These exist so the same model definitions produce a sensible schema on both
SQLite (development) and PostgreSQL/Supabase (production) without any
`if dialect == ...` checks leaking into the models.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import CHAR, DateTime, Integer, String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Dialect


class GUID(TypeDecorator):
    """Platform-independent UUID.

    Uses PostgreSQL's native UUID type where available, otherwise stores the
    canonical 36-character hyphenated string in a CHAR(36). Python-side values
    are always `uuid.UUID`, so application code never sees the difference.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class TZDateTime(TypeDecorator):
    """Timezone-aware datetime that survives SQLite.

    SQLite has no native timestamptz and silently drops tzinfo. We normalise to
    UTC on the way in and re-attach UTC on the way out, so the application layer
    only ever handles aware UTC datetimes on both backends.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected; pass an aware UTC datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Rupees(TypeDecorator):
    """Whole-rupee money stored as a plain INTEGER.

    The business deals exclusively in whole rupees (rents like 8000, a flat
    1000 deduction, no partial payments), so an integer is exact, sorts and
    sums correctly, and behaves identically on SQLite and Postgres. Floats are
    deliberately avoided; NUMERIC is avoided because SQLite degrades it to a
    float behind SQLAlchemy's back.
    """

    impl = Integer
    cache_ok = True


def new_uuid() -> uuid.UUID:
    """Primary-key factory. Generated in Python so an INSERT never has to round
    trip to the database and the id is known before flush."""
    return uuid.uuid4()


def utcnow() -> datetime:
    """Aware UTC now. Used as a Python-side default so timestamps behave the
    same on SQLite and Postgres."""
    return datetime.now(timezone.utc)


def today() -> date:
    """Current UTC date, for date-only defaults."""
    return datetime.now(timezone.utc).date()


__all__ = [
    "GUID",
    "TZDateTime",
    "Rupees",
    "String",
    "new_uuid",
    "utcnow",
    "today",
]
