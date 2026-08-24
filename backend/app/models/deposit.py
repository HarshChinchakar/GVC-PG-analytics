"""Security deposits and their refunds.

Deposits are money the business holds on behalf of the resident. They are
never rental revenue and must never be added into collected rent -- keeping
them in their own tables makes mixing them up a deliberate act rather than an
easy accident.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DepositStatus, PaymentMethod, sql_in
from app.core.types import GUID, Rupees
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.resident import Resident, ResidentStay
    from app.models.user import User


class Deposit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One security deposit taken from one resident.

    Tied to the stay as well as the resident, so a resident who leaves and
    later returns has two clearly separate deposits.
    """

    __tablename__ = "deposits"

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
        unique=True,
    )

    amount: Mapped[int] = mapped_column(Rupees(), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentMethod.CASH
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DepositStatus.HELD, index=True
    )

    received_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    resident: Mapped["Resident"] = relationship(back_populates="deposits")
    stay: Mapped["ResidentStay"] = relationship()
    received_by: Mapped["User"] = relationship()
    refund: Mapped["DepositRefund | None"] = relationship(
        back_populates="deposit", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(sql_in("status", DepositStatus), name="deposit_status_valid"),
        CheckConstraint(sql_in("method", PaymentMethod), name="method_valid"),
        # Powers the "deposits held" dashboard figure.
        Index("ix_deposits_location_status", "location_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Deposit {self.amount} {self.status}>"


class DepositRefund(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The settlement of a deposit when a resident leaves.

    Every component is stored rather than only the final number, so the
    arithmetic can be shown and checked at move-out:

        refund_amount = gross_amount - mandatory_deduction - other_deduction

    `mandatory_deduction` is copied from the location's rule at settlement time
    instead of being read live, so changing the house rule later cannot silently
    restate refunds that were already paid out.
    """

    __tablename__ = "deposit_refunds"

    location_id: Mapped[uuid.UUID] = location_fk()
    deposit_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("deposits.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    gross_amount: Mapped[int] = mapped_column(Rupees(), nullable=False)
    mandatory_deduction: Mapped[int] = mapped_column(Rupees(), nullable=False)
    other_deduction: Mapped[int] = mapped_column(Rupees(), nullable=False, default=0)
    other_deduction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_amount: Mapped[int] = mapped_column(Rupees(), nullable=False)

    refunded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    method: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentMethod.CASH
    )
    processed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    deposit: Mapped["Deposit"] = relationship(back_populates="refund")
    processed_by: Mapped["User"] = relationship()

    __table_args__ = (
        CheckConstraint("gross_amount >= 0", name="gross_non_negative"),
        CheckConstraint("mandatory_deduction >= 0", name="mandatory_non_negative"),
        CheckConstraint("other_deduction >= 0", name="other_non_negative"),
        CheckConstraint("refund_amount >= 0", name="refund_non_negative"),
        # The arithmetic is enforced by the database, not merely by the service
        # that writes it. A refund that does not add up cannot be stored.
        CheckConstraint(
            "refund_amount = gross_amount - mandatory_deduction - other_deduction",
            name="refund_arithmetic",
        ),
        CheckConstraint(
            "other_deduction = 0 OR other_deduction_reason IS NOT NULL",
            name="other_deduction_needs_reason",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DepositRefund {self.refund_amount}>"
