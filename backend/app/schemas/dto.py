"""Response shapes returned to the UI.

Requirement 11: database records are never handed to the UI directly. Every
API response is built from one of these models, which means:

  * internal ids that the UI has no use for (stay_id, room_id) stay internal;
  * columns the caller is not entitled to (deposit totals for a manager,
    `password_hash` for anyone) cannot leak by accident, because a field that
    is not declared here simply cannot be serialised;
  * the UI sees the human-readable bed label, never a UUID-shaped room key.

These are read models. Write payloads are separate and validated on entry.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    BedStatus,
    DepositStatus,
    NoticeStatus,
    RentStatus,
    ResidentStatus,
    UserRole,
)


class ORMModel(BaseModel):
    """Base for models read out of ORM objects.

    `from_attributes` lets us build from a mapped instance, but only the fields
    declared on the subclass are ever read -- that is the whole point.
    """

    model_config = ConfigDict(from_attributes=True)


# --- identity ----------------------------------------------------------


class CurrentUser(ORMModel):
    """The signed-in user. Note the absence of password_hash and auth_user_id."""

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    accessible_locations: list["LocationSummary"] = Field(default_factory=list)


class LocationSummary(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    city: str | None = None


# --- physical structure ------------------------------------------------


class BedView(ORMModel):
    """A bed as the UI shows it: label first, resident name inline.

    `default_rent` is included because the vacant-bed list needs it to show
    what each empty bed is costing.
    """

    id: uuid.UUID
    label: str
    bed_number: int
    status: BedStatus
    is_attached: bool
    default_rent: int
    resident_id: uuid.UUID | None = None
    resident_name: str | None = None
    monthly_rent: int | None = None
    expected_vacant_on: date | None = None


class RoomView(ORMModel):
    id: uuid.UUID
    name: str
    room_kind: str
    is_attached: bool
    beds: list[BedView] = Field(default_factory=list)


class FlatView(ORMModel):
    id: uuid.UUID
    flat_number: str
    flat_type: str
    floor_name: str
    rooms: list[RoomView] = Field(default_factory=list)


# --- residents ---------------------------------------------------------


class ResidentListItem(ORMModel):
    """One row of the residents table."""

    id: uuid.UUID
    full_name: str
    phone: str
    status: ResidentStatus
    flat_number: str | None = None
    bed_label: str | None = None
    monthly_rent: int | None = None
    joined_on: date
    current_month_rent_status: RentStatus | None = None
    expected_move_out_date: date | None = None


class LedgerLine(ORMModel):
    """One month of a resident's rent history."""

    period_year: int
    period_month: int
    period_label: str
    amount_due: int
    status: RentStatus
    paid_on: date | None = None
    marked_by: str | None = None


class ResidentDetail(ORMModel):
    """The resident ledger screen."""

    id: uuid.UUID
    full_name: str
    phone: str
    alt_phone: str | None = None
    status: ResidentStatus
    joined_on: date
    left_on: date | None = None
    location_name: str
    flat_number: str | None = None
    bed_label: str | None = None
    monthly_rent: int | None = None
    deposit_amount: int | None = None
    deposit_status: DepositStatus | None = None
    notes: str | None = None
    ledger: list[LedgerLine] = Field(default_factory=list)
    notice: "NoticeView | None" = None


# --- rent --------------------------------------------------------------


class RentRow(ORMModel):
    """One line of the monthly rent screen."""

    rent_record_id: uuid.UUID
    resident_id: uuid.UUID
    resident_name: str
    phone: str
    flat_number: str | None = None
    bed_label: str | None = None
    amount_due: int
    status: RentStatus
    due_date: date
    paid_on: date | None = None
    marked_by: str | None = None


class RentMonthSummary(ORMModel):
    period_year: int
    period_month: int
    period_label: str
    expected_rent: int
    collected_rent: int
    pending_rent: int
    collection_rate: float
    paid_count: int
    pending_count: int


# --- move-outs ---------------------------------------------------------


class NoticeView(ORMModel):
    id: uuid.UUID
    resident_id: uuid.UUID
    resident_name: str
    phone: str
    bed_label: str | None = None
    notice_date: date
    expected_move_out_date: date
    actual_move_out_date: date | None = None
    status: NoticeStatus
    days_remaining: int | None = None


# --- deposits ----------------------------------------------------------


class DepositView(ORMModel):
    """Deposit settlement, with the arithmetic spelled out for verification."""

    resident_id: uuid.UUID
    resident_name: str
    amount: int
    received_on: date
    status: DepositStatus
    mandatory_deduction: int | None = None
    other_deduction: int | None = None
    refund_amount: int | None = None
    refunded_on: date | None = None


# --- dashboard ---------------------------------------------------------


class OccupancyStats(ORMModel):
    total_beds: int
    occupied: int
    available: int
    on_notice: int
    booked: int
    blocked: int
    occupancy_rate: float


class VacancyStats(ORMModel):
    vacant_beds: int
    potential_monthly_loss: int


class DashboardView(ORMModel):
    """The location dashboard.

    `deposits_held` is optional because a manager does not see it -- the
    service leaves it unset for that role rather than the UI hiding it.
    """

    location_id: uuid.UUID
    location_name: str
    period_label: str
    occupancy: OccupancyStats
    rent: RentMonthSummary
    vacancy: VacancyStats
    upcoming_move_outs_30d: int
    deposits_held: int | None = None
    pending_refunds: int | None = None
    generated_at: datetime


CurrentUser.model_rebuild()
ResidentDetail.model_rebuild()
