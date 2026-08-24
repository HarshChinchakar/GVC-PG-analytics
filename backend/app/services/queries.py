"""Read services.

These are the queries the dashboard and the operational screens are built on.
They live here rather than in route handlers so that the tenant predicate is
applied in exactly one place per question, and so the API layer has nothing to
do but serialise a DTO.

Every public function takes an `AccessContext` and returns DTOs -- never ORM
instances. That is the boundary requirement 11 asks for.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    BedStatus,
    DepositStatus,
    NoticeStatus,
    RentStatus,
    ResidentStatus,
)
from app.core.types import utcnow
from app.models import (
    Bed,
    Deposit,
    DepositRefund,
    Flat,
    MoveOutNotice,
    Payment,
    RentRecord,
    Resident,
    ResidentStay,
    Room,
    User,
)
from app.models.location import Location
from app.schemas.dto import (
    BedView,
    DashboardView,
    LedgerLine,
    NoticeView,
    OccupancyStats,
    RentMonthSummary,
    RentRow,
    ResidentDetail,
    VacancyStats,
)
from app.services.access import AccessContext, AccessDenied


def _month_label(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%B %Y")


# --- occupancy ----------------------------------------------------------


def occupancy_stats(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> OccupancyStats:
    """Bed counts for one building, derived entirely from bed status.

    BLOCKED beds are excluded from the occupancy denominator: a bed under
    repair is not lost revenue the owner can act on, and counting it as vacant
    would understate occupancy every time something breaks.
    """
    ctx.require(location_id)

    rows = db.execute(
        select(Bed.status, func.count())
        .where(Bed.location_id == location_id, Bed.is_active.is_(True))
        .group_by(Bed.status)
    ).all()
    by_status = {status: count for status, count in rows}

    occupied = by_status.get(BedStatus.OCCUPIED, 0)
    on_notice = by_status.get(BedStatus.NOTICE, 0)
    available = by_status.get(BedStatus.AVAILABLE, 0)
    booked = by_status.get(BedStatus.BOOKED, 0)
    blocked = by_status.get(BedStatus.BLOCKED, 0)

    # A booked bed is rentable but nobody is in it yet, so it sits in the
    # denominator and not the numerator -- it correctly drags occupancy down
    # until the person actually arrives.
    rentable = occupied + on_notice + available + booked
    # A resident under notice is still living there and still paying.
    filled = occupied + on_notice

    return OccupancyStats(
        total_beds=rentable + blocked,
        occupied=occupied,
        available=available,
        on_notice=on_notice,
        booked=booked,
        blocked=blocked,
        occupancy_rate=round(filled / rentable * 100, 1) if rentable else 0.0,
    )


def vacancy_stats(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> VacancyStats:
    """Empty beds and what they are costing.

    The loss is the sum of each empty bed's own `default_rent`, not a count
    multiplied by an average -- which is why beds carry a rent of their own.
    """
    ctx.require(location_id)

    count, loss = db.execute(
        select(func.count(), func.coalesce(func.sum(Bed.default_rent), 0)).where(
            Bed.location_id == location_id,
            Bed.is_active.is_(True),
            Bed.status == BedStatus.AVAILABLE,
        )
    ).one()

    return VacancyStats(vacant_beds=count, potential_monthly_loss=int(loss))


# --- rent ---------------------------------------------------------------


def rent_summary(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    year: int,
    month: int,
) -> RentMonthSummary:
    """Expected vs collected vs pending for one month.

    Computed in a single aggregate pass over rent_records. Waived rent is
    excluded from expected so a correction does not permanently show as a
    shortfall.
    """
    ctx.require(location_id)

    expected, collected, paid_count, pending_count = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case((RentRecord.status != RentStatus.WAIVED, RentRecord.amount_due), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((RentRecord.status == RentStatus.PAID, RentRecord.amount_due), else_=0)
                ),
                0,
            ),
            func.sum(case((RentRecord.status == RentStatus.PAID, 1), else_=0)),
            func.sum(case((RentRecord.status == RentStatus.PENDING, 1), else_=0)),
        ).where(
            RentRecord.location_id == location_id,
            RentRecord.period_year == year,
            RentRecord.period_month == month,
        )
    ).one()

    expected, collected = int(expected), int(collected)
    return RentMonthSummary(
        period_year=year,
        period_month=month,
        period_label=_month_label(year, month),
        expected_rent=expected,
        collected_rent=collected,
        pending_rent=expected - collected,
        collection_rate=round(collected / expected * 100, 1) if expected else 0.0,
        paid_count=int(paid_count or 0),
        pending_count=int(pending_count or 0),
    )


def rent_rows(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    year: int,
    month: int,
    *,
    status: RentStatus | None = None,
) -> list[RentRow]:
    """The monthly rent table, or the defaulters list when `status` is PENDING.

    One query with joins rather than a query per resident -- the pending list
    is opened many times a day and must not degrade with resident count.
    """
    ctx.require(location_id)

    stmt = (
        select(
            RentRecord.id,
            Resident.id,
            Resident.full_name,
            Resident.phone,
            Flat.flat_number,
            Bed.label,
            RentRecord.amount_due,
            RentRecord.status,
            RentRecord.due_date,
            Payment.paid_on,
            User.full_name,
        )
        .join(Resident, Resident.id == RentRecord.resident_id)
        .join(ResidentStay, ResidentStay.id == RentRecord.stay_id)
        .join(Bed, Bed.id == ResidentStay.bed_id)
        .join(Room, Room.id == Bed.room_id)
        .join(Flat, Flat.id == Room.flat_id)
        .outerjoin(Payment, Payment.rent_record_id == RentRecord.id)
        .outerjoin(User, User.id == Payment.marked_by_user_id)
        .where(
            RentRecord.location_id == location_id,
            RentRecord.period_year == year,
            RentRecord.period_month == month,
        )
        .order_by(Flat.flat_number, Bed.label)
    )
    if status is not None:
        stmt = stmt.where(RentRecord.status == status)

    return [
        RentRow(
            rent_record_id=row[0],
            resident_id=row[1],
            resident_name=row[2],
            phone=row[3],
            flat_number=row[4],
            bed_label=row[5],
            amount_due=row[6],
            status=row[7],
            due_date=row[8],
            paid_on=row[9],
            marked_by=row[10],
        )
        for row in db.execute(stmt).all()
    ]


def resident_ledger(
    db: Session, ctx: AccessContext, resident_id: uuid.UUID
) -> list[LedgerLine]:
    """A resident's month-by-month rent history, newest last."""
    stmt = (
        select(
            RentRecord.period_year,
            RentRecord.period_month,
            RentRecord.amount_due,
            RentRecord.status,
            Payment.paid_on,
            User.full_name,
            RentRecord.location_id,
        )
        .outerjoin(Payment, Payment.rent_record_id == RentRecord.id)
        .outerjoin(User, User.id == Payment.marked_by_user_id)
        .where(RentRecord.resident_id == resident_id)
        .order_by(RentRecord.period_year, RentRecord.period_month)
    )
    rows = db.execute(stmt).all()
    if rows and not ctx.can_access(rows[0][6]):
        raise AccessDenied()

    return [
        LedgerLine(
            period_year=row[0],
            period_month=row[1],
            period_label=_month_label(row[0], row[1]),
            amount_due=row[2],
            status=row[3],
            paid_on=row[4],
            marked_by=row[5],
        )
        for row in rows
    ]


# --- move-outs ----------------------------------------------------------


def upcoming_move_outs(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    *,
    within_days: int = 30,
    today: date | None = None,
) -> list[NoticeView]:
    """Residents due to leave within the window, soonest first."""
    ctx.require(location_id)
    today = today or date.today()
    horizon = today + timedelta(days=within_days)

    stmt = (
        select(
            MoveOutNotice.id,
            Resident.id,
            Resident.full_name,
            Resident.phone,
            Bed.label,
            MoveOutNotice.notice_date,
            MoveOutNotice.expected_move_out_date,
            MoveOutNotice.actual_move_out_date,
            MoveOutNotice.status,
        )
        .join(Resident, Resident.id == MoveOutNotice.resident_id)
        .join(ResidentStay, ResidentStay.id == MoveOutNotice.stay_id)
        .join(Bed, Bed.id == ResidentStay.bed_id)
        .where(
            MoveOutNotice.location_id == location_id,
            MoveOutNotice.status == NoticeStatus.ACTIVE,
            MoveOutNotice.expected_move_out_date <= horizon,
        )
        .order_by(MoveOutNotice.expected_move_out_date)
    )

    return [
        NoticeView(
            id=row[0],
            resident_id=row[1],
            resident_name=row[2],
            phone=row[3],
            bed_label=row[4],
            notice_date=row[5],
            expected_move_out_date=row[6],
            actual_move_out_date=row[7],
            status=row[8],
            days_remaining=(row[6] - today).days,
        )
        for row in db.execute(stmt).all()
    ]


# --- dashboard ----------------------------------------------------------


def dashboard(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    year: int,
    month: int,
    *,
    today: date | None = None,
) -> DashboardView:
    """The whole location dashboard in one call.

    Deposit figures are attached only for the owner. A manager receives a
    DashboardView with those fields left as None -- the data never leaves the
    service, rather than being sent and hidden by the UI.
    """
    ctx.require(location_id)
    today = today or date.today()

    location = db.get(Location, location_id)
    if location is None:
        raise AccessDenied()

    occupancy = occupancy_stats(db, ctx, location_id)
    rent = rent_summary(db, ctx, location_id, year, month)
    vacancy = vacancy_stats(db, ctx, location_id)
    move_outs = len(upcoming_move_outs(db, ctx, location_id, today=today))

    deposits_held: int | None = None
    pending_refunds: int | None = None
    if ctx.is_super_admin:
        deposits_held = int(
            db.scalar(
                select(func.coalesce(func.sum(Deposit.amount), 0)).where(
                    Deposit.location_id == location_id,
                    Deposit.status == DepositStatus.HELD,
                )
            )
            or 0
        )
        pending_refunds = int(
            db.scalar(
                select(func.coalesce(func.sum(DepositRefund.refund_amount), 0)).where(
                    DepositRefund.location_id == location_id,
                    DepositRefund.refunded_on.is_(None),
                )
            )
            or 0
        )

    return DashboardView(
        location_id=location.id,
        location_name=location.name,
        period_label=_month_label(year, month),
        occupancy=occupancy,
        rent=rent,
        vacancy=vacancy,
        upcoming_move_outs_30d=move_outs,
        deposits_held=deposits_held,
        pending_refunds=pending_refunds,
        generated_at=utcnow(),
    )


# --- operational lists --------------------------------------------------


def vacant_beds(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> list[BedView]:
    """Every rentable empty bed, with what it would earn.

    BLOCKED beds are excluded: they are not sellable, so listing them under
    "vacant" would send staff chasing capacity that does not exist.
    """
    ctx.require(location_id)

    stmt = (
        select(Bed.id, Bed.label, Bed.bed_number, Bed.status, Room.is_attached,
               Bed.default_rent, Flat.flat_number)
        .join(Room, Room.id == Bed.room_id)
        .join(Flat, Flat.id == Room.flat_id)
        .where(
            Bed.location_id == location_id,
            Bed.is_active.is_(True),
            Bed.status == BedStatus.AVAILABLE,
        )
        .order_by(Flat.flat_number, Bed.bed_number)
    )
    return [
        BedView(
            id=r[0], label=r[1], bed_number=r[2], status=r[3],
            is_attached=r[4], default_rent=r[5],
        )
        for r in db.execute(stmt).all()
    ]


def beds_freeing_soon(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> list[BedView]:
    """Beds under notice, with the date they free up.

    Distinct from vacant beds: these are still occupied and still earning, but
    the owner can start filling them now.
    """
    ctx.require(location_id)

    stmt = (
        select(Bed.id, Bed.label, Bed.bed_number, Bed.status, Room.is_attached,
               Bed.default_rent, Resident.id, Resident.full_name,
               ResidentStay.monthly_rent, MoveOutNotice.expected_move_out_date)
        .join(Room, Room.id == Bed.room_id)
        .join(ResidentStay, and_(ResidentStay.bed_id == Bed.id,
                                 ResidentStay.is_current.is_(True)))
        .join(Resident, Resident.id == ResidentStay.resident_id)
        .join(MoveOutNotice, and_(MoveOutNotice.stay_id == ResidentStay.id,
                                  MoveOutNotice.status == NoticeStatus.ACTIVE))
        .where(Bed.location_id == location_id, Bed.status == BedStatus.NOTICE)
        .order_by(MoveOutNotice.expected_move_out_date)
    )
    return [
        BedView(
            id=r[0], label=r[1], bed_number=r[2], status=r[3], is_attached=r[4],
            default_rent=r[5], resident_id=r[6], resident_name=r[7],
            monthly_rent=r[8], expected_vacant_on=r[9],
        )
        for r in db.execute(stmt).all()
    ]


def deposit_totals(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> tuple[int, int, int]:
    """(held, refunded_to_date, approved_but_unpaid) for one building.

    Owner-only figures. Kept as a single function so the three numbers can
    never be computed from inconsistent snapshots.
    """
    ctx.require(location_id)

    held = db.scalar(
        select(func.coalesce(func.sum(Deposit.amount), 0)).where(
            Deposit.location_id == location_id, Deposit.status == DepositStatus.HELD
        )
    )
    refunded = db.scalar(
        select(func.coalesce(func.sum(DepositRefund.refund_amount), 0)).where(
            DepositRefund.location_id == location_id,
            DepositRefund.refunded_on.is_not(None),
        )
    )
    pending = db.scalar(
        select(func.coalesce(func.sum(DepositRefund.refund_amount), 0)).where(
            DepositRefund.location_id == location_id,
            DepositRefund.refunded_on.is_(None),
        )
    )
    return int(held or 0), int(refunded or 0), int(pending or 0)


def resident_counts(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> dict[str, int]:
    """Head-count by resident status, for the month-end summary."""
    ctx.require(location_id)
    rows = db.execute(
        select(Resident.status, func.count())
        .where(Resident.location_id == location_id)
        .group_by(Resident.status)
    ).all()
    counts = {status: count for status, count in rows}
    return {
        "active": counts.get(ResidentStatus.ACTIVE, 0),
        "notice": counts.get(ResidentStatus.NOTICE, 0),
        "left": counts.get(ResidentStatus.LEFT, 0),
        "living_here": counts.get(ResidentStatus.ACTIVE, 0)
        + counts.get(ResidentStatus.NOTICE, 0),
    }


def available_periods(
    db: Session, ctx: AccessContext, location_id: uuid.UUID
) -> list[tuple[int, int]]:
    """Months that actually have rent data, newest first.

    The month picker is driven by this rather than by a date range, so the UI
    can never offer a month with nothing behind it.
    """
    ctx.require(location_id)
    rows = db.execute(
        select(RentRecord.period_year, RentRecord.period_month)
        .where(RentRecord.location_id == location_id)
        .group_by(RentRecord.period_year, RentRecord.period_month)
        .order_by(RentRecord.period_year.desc(), RentRecord.period_month.desc())
    ).all()
    return [(int(y), int(m)) for y, m in rows]
