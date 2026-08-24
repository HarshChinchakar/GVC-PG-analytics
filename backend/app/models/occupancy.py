"""Advance bookings and resident vehicles.

Both exist to answer questions the seat map has to answer: is this empty bed
really available, and whose vehicle is that outside.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReservationStatus, VehicleType, sql_in
from app.core.types import GUID, Rupees
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.location import Bed
    from app.models.resident import Resident
    from app.models.user import User


class BedReservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A bed promised to someone who has not arrived yet.

    Deliberately NOT modelled as a `resident_stay` with a future start date.
    A stay means someone is living in a bed and owes rent for it; the two
    partial unique indexes and the `is_current`/`end_date` CHECK on that table
    all assume exactly that. Bending it to hold a person who has not shown up,
    owes nothing, and may never arrive would weaken the guarantees that make
    occupancy trustworthy.

    The person is stored inline rather than as a `Resident` row for the same
    reason: they are not a resident until they move in, and a half-real
    resident record would show up in head-counts and rent runs.
    """

    __tablename__ = "bed_reservations"

    location_id: Mapped[uuid.UUID] = location_fk()
    bed_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("beds.id", ondelete="CASCADE"), nullable=False, index=True
    )

    person_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)

    expected_move_in: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: Advance taken to hold the bed. Not rent, and not a deposit -- it is
    #: settled against one of those when the person actually arrives.
    token_amount: Mapped[int] = mapped_column(Rupees(), nullable=False, default=0)
    agreed_rent: Mapped[int | None] = mapped_column(Rupees(), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReservationStatus.HELD, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    #: Set when the booking becomes a real tenancy.
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("residents.id", ondelete="SET NULL"), nullable=True
    )

    bed: Mapped["Bed"] = relationship()
    created_by: Mapped["User"] = relationship()

    __table_args__ = (
        CheckConstraint(sql_in("status", ReservationStatus), name="reservation_status_valid"),
        CheckConstraint("token_amount >= 0", name="token_non_negative"),
        CheckConstraint("agreed_rent IS NULL OR agreed_rent >= 0", name="agreed_rent_non_negative"),
        CheckConstraint("length(trim(person_name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(phone)) > 0", name="phone_not_blank"),
        # One live booking per bed. Without this two staff could promise the
        # same bed to two people on the same afternoon.
        Index(
            "uq_bed_single_active_reservation",
            "bed_id",
            unique=True,
            sqlite_where=text("status = 'held'"),
            postgresql_where=text("status = 'held'"),
        ),
        Index("ix_reservations_location_status", "location_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reservation {self.person_name} -> {self.expected_move_in}>"


def normalise_plate(raw: str) -> str:
    """Strip a registration to letters and digits, uppercased.

    People write the same plate as "MH12AB4472", "MH 12 AB 4472" and
    "mh-12-ab-4472". Searching has to ignore all of that, so the normalised
    form is stored alongside the one the owner typed and every lookup is done
    against it.
    """
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


class Vehicle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A vehicle belonging to a resident.

    Exists to answer one question fast, usually at the gate: whose is this?
    """

    __tablename__ = "vehicles"

    location_id: Mapped[uuid.UUID] = location_fk()
    resident_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("residents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: As written on the plate, for display.
    vehicle_number: Mapped[str] = mapped_column(String(24), nullable=False)
    #: Letters and digits only -- the column every search runs against.
    number_normalised: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    vehicle_type: Mapped[str] = mapped_column(String(20), nullable=False)
    make_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(40), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    resident: Mapped["Resident"] = relationship(back_populates="vehicles")

    __table_args__ = (
        CheckConstraint(sql_in("vehicle_type", VehicleType), name="vehicle_type_valid"),
        CheckConstraint("length(trim(number_normalised)) > 3", name="plate_long_enough"),
        # The same plate cannot be registered twice in one building -- that
        # would make the gate lookup ambiguous, which is the one thing it
        # must never be.
        UniqueConstraint("location_id", "number_normalised", name="plate_unique_per_location"),
        Index("ix_vehicles_location_number", "location_id", "number_normalised"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vehicle {self.vehicle_number}>"
