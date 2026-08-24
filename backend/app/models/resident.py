"""Residents and their bed assignments.

A resident is a person; a *stay* is one continuous occupation of one bed at one
rent. Separating them is what makes the rest of the system honest:

  * a resident who moves from bed 101-1NA to 204-2A gets a second stay, so the
    history of who slept where stays correct;
  * rent, deposit and move-out notice all hang off the stay, so a rent change
    on transfer cannot retroactively rewrite last month's ledger;
  * occupancy is simply "stays with no end date".
"""

from __future__ import annotations

import uuid
from datetime import date
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

from app.core.enums import Gender, ResidentStatus, sql_in
from app.core.types import GUID, Rupees
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.deposit import Deposit
    from app.models.location import Bed
    from app.models.moveout import MoveOutNotice
    from app.models.occupancy import Vehicle
    from app.models.rent import RentRecord


class Resident(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person living (or who lived) in one PG.

    Deliberately small -- Project.md asks for an operational record, not an HR
    profile. A resident belongs to exactly one location; someone who moves
    between buildings is a new record there, which keeps isolation absolute.
    """

    __tablename__ = "residents"

    location_id: Mapped[uuid.UUID] = location_fk()

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Required, not optional: flats are allocated by gender, so a resident
    # without one cannot be placed, and the revenue split would have a silent
    # "unknown" bucket that grows over time.
    gender: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    alt_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Enough to identify someone at move-in; nothing more.
    id_proof_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    id_proof_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    permanent_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ResidentStatus.ACTIVE, index=True
    )

    # First arrival and final departure across all stays. Convenience columns
    # for the residents list; the authoritative per-bed dates live on stays.
    joined_on: Mapped[date] = mapped_column(Date, nullable=False)
    left_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    stays: Mapped[list["ResidentStay"]] = relationship(
        back_populates="resident", cascade="all, delete-orphan", order_by="ResidentStay.start_date"
    )
    deposits: Mapped[list["Deposit"]] = relationship(back_populates="resident")
    rent_records: Mapped[list["RentRecord"]] = relationship(back_populates="resident")
    notices: Mapped[list["MoveOutNotice"]] = relationship(back_populates="resident")
    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="resident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(sql_in("status", ResidentStatus), name="resident_status_valid"),
        CheckConstraint(sql_in("gender", Gender), name="resident_gender_valid"),
        CheckConstraint("length(trim(full_name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(phone)) > 0", name="phone_not_blank"),
        CheckConstraint(
            "left_on IS NULL OR left_on >= joined_on", name="left_after_joined"
        ),
        # A phone number identifies a resident within a building; the same
        # number may legitimately appear in a different building.
        UniqueConstraint("location_id", "phone", name="resident_phone_unique"),
        # Drives the residents screen: "active residents in this PG".
        Index("ix_residents_location_status", "location_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Resident {self.full_name} {self.status}>"


class ResidentStay(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One continuous occupation of one bed by one resident at one rent.

    `end_date IS NULL` means "currently living here", and it is the single
    source of truth for occupancy. `beds.status` is a maintained cache of the
    same fact, kept fast for dashboard counts.
    """

    __tablename__ = "resident_stays"

    location_id: Mapped[uuid.UUID] = location_fk()
    resident_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("residents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bed_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("beds.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # The rent agreed for THIS stay. Frozen here rather than read from the
    # resident so that a later rent revision cannot rewrite past months.
    monthly_rent: Mapped[int] = mapped_column(Rupees(), nullable=False)

    # Day of month the rent falls due, usually the joining day.
    rent_due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    end_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)

    resident: Mapped["Resident"] = relationship(back_populates="stays")
    bed: Mapped["Bed"] = relationship(back_populates="stays")
    rent_records: Mapped[list["RentRecord"]] = relationship(back_populates="stay")

    __table_args__ = (
        CheckConstraint("monthly_rent >= 0", name="rent_non_negative"),
        CheckConstraint(
            "rent_due_day BETWEEN 1 AND 28", name="due_day_valid"
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="end_after_start"
        ),
        # Keeps the boolean cache and the date in agreement. Written with
        # AND/NOT rather than `= 1` so the same SQL is valid on Postgres, where
        # booleans are not integers.
        CheckConstraint(
            "(is_current AND end_date IS NULL) "
            "OR (NOT is_current AND end_date IS NOT NULL)",
            name="current_matches_end_date",
        ),
        # The two rules that make double-booking impossible at the database
        # level, rather than merely unlikely in application code:
        #   * one bed holds at most one current resident
        #   * one resident holds at most one current bed
        # Partial unique indexes exist on both SQLite and Postgres, so this
        # guarantee survives the Supabase move unchanged.
        Index(
            "uq_bed_single_current_occupant",
            "bed_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current"),
        ),
        Index(
            "uq_resident_single_current_stay",
            "resident_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current"),
        ),
        Index("ix_stays_location_current", "location_id", "is_current"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Stay resident={self.resident_id} bed={self.bed_id} current={self.is_current}>"
