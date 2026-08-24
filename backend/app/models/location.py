"""The physical shape of the business.

    Location (a PG / building)
      └── Floor
            └── Flat        (a 2BHK, 3BHK, or single RK unit)
                  └── Room  (hall / bedroom, attached or not)
                        └── Bed   (one sleeping position, the rentable unit)

Every level below Location also carries `location_id` directly so that tenant
isolation is a single predicate at any depth, never a four-table join.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BedStatus, FlatType, GenderPolicy, RoomKind, sql_in
from app.core.types import GUID, Rupees
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, location_fk

if TYPE_CHECKING:
    from app.models.resident import Resident, ResidentStay
    from app.models.user import UserLocation


class Location(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One PG building. The isolation boundary for the entire application."""

    __tablename__ = "locations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Business rules held per building so the owner can vary them without a
    # deploy. Defaults match the rules stated in Project.md.
    notice_period_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    deposit_deduction: Mapped[int] = mapped_column(Rupees(), nullable=False, default=1000)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    floors: Mapped[list["Floor"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    user_grants: Mapped[list["UserLocation"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("notice_period_days > 0", name="notice_period_positive"),
        CheckConstraint("deposit_deduction >= 0", name="deduction_non_negative"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Location {self.code} {self.name}>"


class Floor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A floor of a building. Kept as a real table rather than a number on the
    flat because the owner filters the pending-rent list by floor."""

    __tablename__ = "floors"

    location_id: Mapped[uuid.UUID] = location_fk()
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    location: Mapped["Location"] = relationship(back_populates="floors")
    flats: Mapped[list["Flat"]] = relationship(
        back_populates="floor", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("location_id", "floor_number", name="floor_number_unique"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Floor {self.name}>"


class Flat(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A flat/unit on a floor, e.g. flat 101 configured as a 2BHK."""

    __tablename__ = "flats"

    location_id: Mapped[uuid.UUID] = location_fk()
    floor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("floors.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # The number residents and staff actually say out loud, e.g. "101".
    flat_number: Mapped[str] = mapped_column(String(20), nullable=False)
    flat_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # Which residents this flat takes. Drives the male/female revenue split and
    # stops a bed being offered to someone who cannot legitimately occupy it.
    gender_policy: Mapped[str] = mapped_column(
        String(10), nullable=False, default=GenderPolicy.MALE, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    floor: Mapped["Floor"] = relationship(back_populates="flats")
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="flat", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("location_id", "flat_number", name="flat_number_unique"),
        CheckConstraint(sql_in("flat_type", FlatType), name="flat_type_valid"),
        CheckConstraint(sql_in("gender_policy", GenderPolicy), name="gender_policy_valid"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Flat {self.flat_number} {self.flat_type}>"


class Room(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A room inside a flat: the hall or one of the bedrooms.

    `is_attached` lives here rather than on the bed because a washroom belongs
    to the room -- every bed in an attached bedroom is an attached bed. The bed
    label denormalises it purely for display.
    """

    __tablename__ = "rooms"

    location_id: Mapped[uuid.UUID] = location_fk()
    flat_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("flats.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    room_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    is_attached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Planned capacity. The real count is `len(beds)`; this records intent so a
    # half-furnished room is visibly under capacity.
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    flat: Mapped["Flat"] = relationship(back_populates="rooms")
    beds: Mapped[list["Bed"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("flat_id", "name", name="room_name_unique"),
        CheckConstraint(sql_in("room_kind", RoomKind), name="room_kind_valid"),
        CheckConstraint("capacity >= 0", name="capacity_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Room {self.name}>"


class Bed(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One sleeping position -- the unit that is actually rented.

    `label` is the human-readable identifier the owner asked for ("101-1NA")
    and is what every screen shows; the UUID never reaches the UI.
    """

    __tablename__ = "beds"

    location_id: Mapped[uuid.UUID] = location_fk()
    room_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    bed_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(40), nullable=False)

    # The rent this bed is expected to fetch when empty. Without it the
    # "potential revenue lost to vacancy" figure has nothing to sum, because a
    # vacant bed has no resident to read a rent from.
    default_rent: Mapped[int] = mapped_column(Rupees(), nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BedStatus.AVAILABLE, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    room: Mapped["Room"] = relationship(back_populates="beds")
    stays: Mapped[list["ResidentStay"]] = relationship(back_populates="bed")

    __table_args__ = (
        UniqueConstraint("room_id", "bed_number", name="bed_number_unique"),
        UniqueConstraint("location_id", "label", name="bed_label_unique"),
        CheckConstraint(sql_in("status", BedStatus), name="bed_status_valid"),
        CheckConstraint("default_rent >= 0", name="default_rent_non_negative"),
        CheckConstraint("bed_number > 0", name="bed_number_positive"),
        # Drives the dashboard's occupancy counts and the vacant-bed list.
        Index("ix_beds_location_status", "location_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Bed {self.label} {self.status}>"
