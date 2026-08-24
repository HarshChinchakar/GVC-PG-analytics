"""Expenses, and the recurring templates that make logging them bearable.

Money out, per site. Together with rent this gives a real financial picture
rather than a revenue-only one.

Two ideas carry the design:

  * **Nothing is ever deleted.** A wrong figure is voided, with a reason and
    an author. Spend that vanishes from the ledger is worse than spend that is
    visibly wrong.
  * **Recurring costs must be one tap.** Site rent and salaries land every
    month; a form that has to be filled twelve times a year is a form that
    stops being filled. Templates carry the fixed detail so recording becomes
    a confirmation, and a partial unique index makes double-booking the same
    month impossible rather than merely unlikely.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ExpenseCategory,
    ExpenseStatus,
    PaidFrom,
    PaymentMethod,
    sql_in,
)
from app.core.types import GUID, Rupees, TZDateTime
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.location import Location
    from app.models.user import User


class ExpenseTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A cost that comes round every month.

    Holds everything that does not change -- the site, the category, who is
    paid, usually how much -- so that recording November's rent is a tap
    rather than a form. `default_amount` is nullable because some recurring
    costs vary: the electricity bill recurs, its figure does not.
    """

    __tablename__ = "expense_templates"

    location_id: Mapped[uuid.UUID] = location_fk()

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    payee: Mapped[str] = mapped_column(String(120), nullable=False)

    default_amount: Mapped[int | None] = mapped_column(Rupees(), nullable=True)
    payment_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentMethod.BANK_TRANSFER
    )
    paid_from: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaidFrom.BUSINESS_ACCOUNT
    )

    #: Day the cost normally falls due. Capped at 28 so every month has one.
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    location: Mapped["Location"] = relationship()
    expenses: Mapped[list["Expense"]] = relationship(back_populates="template")

    __table_args__ = (
        UniqueConstraint("location_id", "name", name="template_name_unique"),
        CheckConstraint(sql_in("category", ExpenseCategory), name="category_valid"),
        CheckConstraint(sql_in("payment_mode", PaymentMethod), name="payment_mode_valid"),
        CheckConstraint(sql_in("paid_from", PaidFrom), name="paid_from_valid"),
        CheckConstraint("day_of_month BETWEEN 1 AND 28", name="day_of_month_valid"),
        CheckConstraint(
            "default_amount IS NULL OR default_amount > 0", name="default_amount_positive"
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_templates_location_active", "location_id", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExpenseTemplate {self.name}>"


class Expense(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One payment out, always attached to one site."""

    __tablename__ = "expenses"

    location_id: Mapped[uuid.UUID] = location_fk()

    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    #: Who received the money -- the shop, the electrician, the staff member.
    payee: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    amount: Mapped[int] = mapped_column(Rupees(), nullable=False)

    #: When the money was spent, which is not when it was typed in. Both are
    #: kept: `expense_date` drives the accounts, `created_at` the audit trail.
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    #: The accounting month, as two integers for the same reason rent records
    #: use them (ADR-007). Derived from `expense_date` by one factory function
    #: -- the database cannot enforce the correspondence portably, because
    #: SQLite and Postgres extract date parts with different syntax, so
    #: `crosscheck.py` asserts it on every row instead.
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)

    payment_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    paid_from: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaidFrom.SITE_CASH
    )
    #: Only meaningful when `paid_from` is PERSONAL: someone is owed this back.
    reimbursed_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExpenseStatus.RECORDED, index=True
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    #: Who actually spent the money, and who typed it in. Often the same person,
    #: but a manager buys the cleaning supplies and the owner may file it.
    paid_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("expense_templates.id", ondelete="SET NULL"), nullable=True
    )

    #: Supplied by the client, one per form instance. The unique constraint
    #: turns a double-tapped Save -- or a retried request on a flaky phone
    #: connection -- into a no-op instead of a duplicate payment on the books.
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        GUID(), nullable=False, unique=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped["ExpenseTemplate | None"] = relationship(back_populates="expenses")
    paid_by: Mapped["User"] = relationship(foreign_keys=[paid_by_user_id])
    recorded_by: Mapped["User"] = relationship(foreign_keys=[recorded_by_user_id])

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(sql_in("category", ExpenseCategory), name="category_valid"),
        CheckConstraint(sql_in("status", ExpenseStatus), name="status_valid"),
        CheckConstraint(sql_in("payment_mode", PaymentMethod), name="payment_mode_valid"),
        CheckConstraint(sql_in("paid_from", PaidFrom), name="paid_from_valid"),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="period_month_valid"),
        CheckConstraint("period_year BETWEEN 2000 AND 2200", name="period_year_valid"),
        CheckConstraint("length(trim(payee)) > 0", name="payee_not_blank"),
        # A void must say why, and by whom. Voiding without a reason is how a
        # ledger quietly loses money.
        CheckConstraint(
            "status <> 'void' OR (void_reason IS NOT NULL AND voided_by_user_id IS NOT NULL)",
            name="void_needs_reason_and_author",
        ),
        # Only money someone fronted personally can be reimbursed.
        CheckConstraint(
            "reimbursed_on IS NULL OR paid_from = 'personal'",
            name="only_personal_spend_is_reimbursed",
        ),
        # The rule that makes recurring costs safe: one live booking per
        # template per month. Recording October's rent twice is rejected by
        # the database, not merely discouraged by the UI.
        Index(
            "uq_template_once_per_month",
            "template_id",
            "period_year",
            "period_month",
            unique=True,
            sqlite_where=text("template_id IS NOT NULL AND status = 'recorded'"),
            postgresql_where=text("template_id IS NOT NULL AND status = 'recorded'"),
        ),
        # The monthly expense tally, per site -- the most-run query here.
        Index(
            "ix_expenses_location_period_status",
            "location_id", "period_year", "period_month", "status",
        ),
        Index("ix_expenses_location_category", "location_id", "category"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Expense {self.category} {self.amount} {self.status}>"
