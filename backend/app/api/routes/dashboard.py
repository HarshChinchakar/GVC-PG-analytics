"""Location selection and the dashboard.

The dashboard is served by ONE endpoint returning ONE consistent snapshot.
Splitting it into a call per card would let the numbers disagree with each
other -- occupancy read before a move-out, rent read after it -- and the whole
point of the screen is that its figures reconcile.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import Ctx, Db
from app.core.enums import RentStatus
from app.schemas.dto import (
    BedView,
    NoticeView,
    OccupancyStats,
    RentMonthSummary,
    RentRow,
    VacancyStats,
)
from app.services import analysis, occupancy as occupancy_service, queries
from app.services.access import AccessDenied
from app.models import Location
from sqlalchemy import select

router = APIRouter(tags=["dashboard"])


class LocationCard(BaseModel):
    """A building on the site-picker screen, with just enough live data to
    choose between them at a glance."""

    id: str
    name: str
    code: str
    city: str | None
    total_beds: int
    occupied: int
    available: int
    occupancy_rate: float
    pending_rent: int
    pending_count: int


class DepositSummary(BaseModel):
    held: int
    refunded_to_date: int
    approved_unpaid: int


class ResidentCounts(BaseModel):
    active: int
    notice: int
    left: int
    living_here: int


class DashboardResponse(BaseModel):
    """Everything the dashboard renders, from one point in time."""

    location_id: str
    location_name: str
    location_code: str
    period_year: int
    period_month: int
    period_label: str
    available_periods: list[str]

    occupancy: OccupancyStats
    rent: RentMonthSummary
    vacancy: VacancyStats
    residents: ResidentCounts
    deposits: DepositSummary | None

    pending_payments: list[RentRow]
    vacant_beds: list[BedView]
    freeing_soon: list[BedView]
    upcoming_move_outs: list[NoticeView]

    generated_at: str


def _resolve(db, ctx, location_id: str) -> Location:
    try:
        parsed = uuid.UUID(location_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
    location = db.get(Location, parsed)
    if location is None or not ctx.can_access(location.id):
        # 404 not 403 -- a manager must not learn other buildings exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return location


@router.get("/locations", response_model=list[LocationCard])
def list_locations(ctx: Ctx, db: Db) -> list[LocationCard]:
    """Buildings this user may open, each with a live summary.

    This is the screen the owner lands on after signing in.
    """
    today = date.today()
    stmt = select(Location).where(Location.is_active.is_(True))
    if not ctx.is_super_admin:
        if not ctx.location_ids:
            return []
        stmt = stmt.where(Location.id.in_(ctx.location_ids))

    cards: list[LocationCard] = []
    for loc in db.scalars(stmt.order_by(Location.name)).all():
        occupancy = queries.occupancy_stats(db, ctx, loc.id)
        rent = queries.rent_summary(db, ctx, loc.id, today.year, today.month)
        cards.append(
            LocationCard(
                id=str(loc.id),
                name=loc.name,
                code=loc.code,
                city=loc.city,
                total_beds=occupancy.total_beds,
                occupied=occupancy.occupied + occupancy.on_notice,
                available=occupancy.available,
                occupancy_rate=occupancy.occupancy_rate,
                pending_rent=rent.pending_rent,
                pending_count=rent.pending_count,
            )
        )
    return cards


@router.get("/locations/{location_id}/dashboard", response_model=DashboardResponse)
def dashboard(
    location_id: str,
    ctx: Ctx,
    db: Db,
    year: int | None = Query(None, ge=2000, le=2200),
    month: int | None = Query(None, ge=1, le=12),
) -> DashboardResponse:
    """The complete overview for one building and one month."""
    location = _resolve(db, ctx, location_id)
    today = date.today()
    year = year or today.year
    month = month or today.month

    try:
        occupancy = queries.occupancy_stats(db, ctx, location.id)
        rent = queries.rent_summary(db, ctx, location.id, year, month)
        vacancy = queries.vacancy_stats(db, ctx, location.id)
        counts = queries.resident_counts(db, ctx, location.id)
        pending = queries.rent_rows(
            db, ctx, location.id, year, month, status=RentStatus.PENDING
        )
        vacant = queries.vacant_beds(db, ctx, location.id)
        freeing = queries.beds_freeing_soon(db, ctx, location.id)
        move_outs = queries.upcoming_move_outs(db, ctx, location.id, today=today)
        periods = queries.available_periods(db, ctx, location.id)
    except AccessDenied:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    deposits = None
    if ctx.is_super_admin:
        held, refunded, unpaid = queries.deposit_totals(db, ctx, location.id)
        deposits = DepositSummary(
            held=held, refunded_to_date=refunded, approved_unpaid=unpaid
        )

    from app.core.types import utcnow

    return DashboardResponse(
        location_id=str(location.id),
        location_name=location.name,
        location_code=location.code,
        period_year=year,
        period_month=month,
        period_label=date(year, month, 1).strftime("%B %Y"),
        available_periods=[f"{y}-{m:02d}" for y, m in periods],
        occupancy=occupancy,
        rent=rent,
        vacancy=vacancy,
        residents=ResidentCounts(**counts),
        deposits=deposits,
        pending_payments=pending,
        vacant_beds=vacant,
        freeing_soon=freeing,
        upcoming_move_outs=move_outs,
        generated_at=utcnow().isoformat(),
    )


@router.get("/locations/{location_id}/analysis")
def revenue_analysis(
    location_id: str,
    ctx: Ctx,
    db: Db,
    year: int | None = Query(None, ge=2000, le=2200),
    month: int | None = Query(None, ge=1, le=12),
) -> dict:
    """The revenue drill-down behind the rent card.

    Returns a plain dict rather than a declared response model: the shape is a
    list of dimensions whose segments all share one schema, and pinning it to
    a Pydantic model here would mean redeclaring that schema for every
    dimension without adding any safety -- the values are computed server-side
    from typed dataclasses, never accepted from a client.

    Owner-only. A manager runs a building day to day; portfolio economics,
    pricing leakage and yield analysis are the owner's business (Project.md
    §4.2).
    """
    location = _resolve(db, ctx, location_id)
    if not ctx.is_super_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    today = date.today()
    try:
        return analysis.revenue_analysis(
            db, ctx, location.id, year or today.year, month or today.month
        )
    except AccessDenied:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None


@router.get("/locations/{location_id}/occupancy")
def occupancy_board(
    location_id: str,
    ctx: Ctx,
    db: Db,
    year: int | None = Query(None, ge=2000, le=2200),
    month: int | None = Query(None, ge=1, le=12),
) -> dict:
    """The seat map: every bed in the building, as it sits in the building.

    Available to managers as well as the owner -- this is the operational
    board, not financial analysis. A manager needs to know which bed is free
    and who has not paid far more often than the owner does.
    """
    location = _resolve(db, ctx, location_id)
    today = date.today()
    try:
        return occupancy_service.occupancy_board(
            db, ctx, location.id, year or today.year, month or today.month, today=today
        )
    except AccessDenied:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None


@router.get("/locations/{location_id}/vehicles")
def vehicles(
    location_id: str,
    ctx: Ctx,
    db: Db,
    q: str | None = Query(None, max_length=60),
) -> dict:
    """Vehicle register and lookup. Also available to managers.

    `q` matches a partial plate, a resident name, or a phone number.
    """
    location = _resolve(db, ctx, location_id)
    try:
        results = occupancy_service.search_vehicles(db, ctx, location.id, q)
    except AccessDenied:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    return {
        "location_id": str(location.id),
        "location_name": location.name,
        "location_code": location.code,
        "query": q or "",
        "count": len(results),
        "results": results,
    }
