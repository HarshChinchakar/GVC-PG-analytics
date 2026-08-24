"""Monthly rent obligations and the payments that settle them.

One row per resident per month is generated when the month opens. That row is
the ledger line the owner reads; the payment row records how and when it was
settled, and by whom.
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
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PaymentMethod, RentStatus, sql_in
from app.core.types import GUID, Rupees
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.resident import Resident, ResidentStay
    from app.models.user import User


class RentRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """What one resident owes for one month.

    The period is stored as separate `period_year` / `period_month` integers
    rather than a date. A month is not a day, and storing it as one invites
    off-by-one bugs at month boundaries and timezone conversion; two integers
    sort, group and compare exactly, on both backends.

    `amount_due` is copied from the stay at generation time. If the rent is
    revised later, historical months keep the amount that was actually owed.
    """

    __tablename__ = "rent_records"

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

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)

    amount_due: Mapped[int] = mapped_column(Rupees(), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RentStatus.PENDING, index=True
    )

    # Only meaningful when status is WAIVED; the owner must say why.
    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    resident: Mapped["Resident"] = relationship(back_populates="rent_records")
    stay: Mapped["ResidentStay"] = relationship(back_populates="rent_records")
    payment: Mapped["Payment | None"] = relationship(
        back_populates="rent_record", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        # One bill per stay per month. This is the constraint that makes
        # double-billing and double-counting structurally impossible.
        UniqueConstraint(
            "stay_id", "period_year", "period_month", name="rent_period_unique"
        ),
        CheckConstraint(sql_in("status", RentStatus), name="rent_status_valid"),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="period_month_valid"),
        CheckConstraint("period_year BETWEEN 2000 AND 2200", name="period_year_valid"),
        CheckConstraint("amount_due >= 0", name="amount_due_non_negative"),
        CheckConstraint(
            "status <> 'waived' OR waiver_reason IS NOT NULL",
            name="waiver_needs_reason",
        ),
        # The single most-run query in the application: this month's tally for
        # this building, and the pending-payments list drawn from it.
        Index(
            "ix_rent_location_period_status",
            "location_id",
            "period_year",
            "period_month",
            "status",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rent {self.period_year}-{self.period_month:02d} {self.status}>"


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The act of settling one month's rent.

    Strictly one payment per rent record, enforced by a unique constraint:
    the business takes no partial payments, so there is no allocation logic,
    no running balance, and nothing to reconcile. No money moves through this
    application -- this row only records that the owner saw the money.
    """

    __tablename__ = "payments"

    location_id: Mapped[uuid.UUID] = location_fk()
    rent_record_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("rent_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    amount: Mapped[int] = mapped_column(Rupees(), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentMethod.CASH
    )
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Who ticked it. Required for month-end verification; RESTRICT so a user
    # cannot be deleted out from under the audit trail.
    marked_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rent_record: Mapped["RentRecord"] = relationship(back_populates="payment")
    marked_by: Mapped["User"] = relationship()

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(sql_in("method", PaymentMethod), name="method_valid"),
        Index("ix_payments_location_paid_on", "location_id", "paid_on"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment {self.amount} on {self.paid_on}>"
