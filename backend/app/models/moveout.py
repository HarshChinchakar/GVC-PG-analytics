"""Move-out notices.

A notice is its own record rather than a pair of dates on the resident because
a notice can be withdrawn, and because the owner wants a history of who gave
notice and when -- not just the current state.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import NoticeStatus, sql_in
from app.core.types import GUID
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.resident import Resident, ResidentStay
    from app.models.user import User


class MoveOutNotice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One month's notice served by a resident.

    `expected_move_out_date` is computed as notice_date + the location's notice
    period and then stored, so an agreed exception ("she is leaving on the 5th
    instead") can be recorded without breaking the house rule for everyone else.
    """

    __tablename__ = "move_out_notices"

    location_id: Mapped[uuid.UUID] = location_fk()
    resident_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("residents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stay_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resident_stays.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    notice_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_move_out_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    actual_move_out_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=NoticeStatus.ACTIVE, index=True
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    resident: Mapped["Resident"] = relationship(back_populates="notices")
    stay: Mapped["ResidentStay"] = relationship()
    created_by: Mapped["User"] = relationship()

    __table_args__ = (
        CheckConstraint(sql_in("status", NoticeStatus), name="notice_status_valid"),
        CheckConstraint(
            "expected_move_out_date >= notice_date", name="expected_after_notice"
        ),
        CheckConstraint(
            "actual_move_out_date IS NULL OR actual_move_out_date >= notice_date",
            name="actual_after_notice",
        ),
        # A completed notice must record when the resident actually left.
        CheckConstraint(
            "status <> 'completed' OR actual_move_out_date IS NOT NULL",
            name="completed_needs_actual_date",
        ),
        # Drives the "upcoming move-outs in the next 30 days" dashboard card.
        Index(
            "ix_notices_location_status_expected",
            "location_id",
            "status",
            "expected_move_out_date",
        ),
        # One live notice per stay. A resident cannot serve notice twice
        # without the first being completed or cancelled.
        Index(
            "uq_stay_single_active_notice",
            "stay_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notice {self.resident_id} -> {self.expected_move_out_date}>"
