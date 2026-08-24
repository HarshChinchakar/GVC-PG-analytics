"""Audit trail.

Deliberately one small table, not an event-sourcing system. Its job is to
answer the questions the owner will actually ask: who marked this rent paid,
who changed this rent amount, who released this bed.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from app.core.enums import AuditAction, sql_in
from app.core.types import GUID
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import CheckConstraint


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One recorded change.

    `location_id` is nullable because a few actions (a super admin logging in,
    creating a new location) do not belong to any single building.

    The `changes` column stores JSON as TEXT on SQLite and as JSONB on
    PostgreSQL, via a dialect variant. We never query inside it -- it is read
    only when a human is investigating a specific row -- but JSONB is the
    better default on Postgres and costs nothing to ask for.
    """

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changes: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    user = relationship("User")

    __table_args__ = (
        CheckConstraint(sql_in("action", AuditAction), name="audit_action_valid"),
        Index("ix_audit_location_created", "location_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.action} {self.entity_type}>"
