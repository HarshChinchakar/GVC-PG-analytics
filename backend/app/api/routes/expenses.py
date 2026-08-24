"""Expense routes — the application's first write surface.

Available to managers and owners alike: a manager who buys cleaning supplies
must be able to file it. Which *categories* they may file is decided in the
service layer, not here and not in the form.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.deps import Ctx, Db
from app.models import Location
from app.services import expenses as service
from app.services.access import AccessDenied
from sqlalchemy import select

router = APIRouter(tags=["expenses"])


def _resolve(db, ctx, location_id: str) -> Location:
    try:
        parsed = uuid.UUID(location_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
    location = db.get(Location, parsed)
    if location is None or not ctx.can_access(location.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return location


class ExpenseIn(BaseModel):
    """A filed expense.

    `idempotency_key` is required, not optional. The client mints one per form
    instance; replaying it returns the original row rather than booking the
    money twice. Making it optional would mean the safe path is the one you
    have to remember.
    """

    category: str = Field(max_length=30)
    payee: str = Field(min_length=1, max_length=120)
    amount: int = Field(gt=0, le=100_00_00_000)
    expense_date: date
    payment_mode: str = Field(max_length=20)
    idempotency_key: uuid.UUID

    description: str | None = Field(default=None, max_length=1000)
    payment_reference: str | None = Field(default=None, max_length=80)
    paid_from: str = Field(default="site_cash", max_length=20)
    template_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.get("/locations/{location_id}/expenses")
def list_expenses(
    location_id: str,
    ctx: Ctx,
    db: Db,
    year: int | None = Query(None, ge=2000, le=2200),
    month: int | None = Query(None, ge=1, le=12),
) -> dict:
    """One month of spend for one site, plus what is still due."""
    location = _resolve(db, ctx, location_id)
    today = date.today()
    try:
        view = service.month_view(
            db, ctx, location.id, year or today.year, month or today.month, today=today
        )
    except AccessDenied:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    view["trend"] = service.trend(db, ctx, location.id)
    # Every site this user may file against, for the form's dropdown.
    sites = db.scalars(select(Location).where(Location.is_active.is_(True))).all()
    view["sites"] = [
        {"id": str(s.id), "name": s.name, "code": s.code}
        for s in sorted(sites, key=lambda s: s.name)
        if ctx.can_access(s.id)
    ]
    return view


@router.post("/locations/{location_id}/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(
    location_id: str, payload: ExpenseIn, ctx: Ctx, db: Db, response: Response
) -> dict:
    """File an expense against a site.

    Answers 200 rather than 201 when the idempotency key has been seen before,
    so a client that retries can tell the difference between "created" and
    "already had it" without either being an error.
    """
    location = _resolve(db, ctx, location_id)
    try:
        expense, created = service.record_expense(
            db,
            ctx,
            location_id=location.id,
            category=payload.category,
            payee=payload.payee,
            amount=payload.amount,
            expense_date=payload.expense_date,
            payment_mode=payload.payment_mode,
            idempotency_key=payload.idempotency_key,
            description=payload.description,
            payment_reference=payload.payment_reference,
            paid_from=payload.paid_from,
            template_id=payload.template_id,
            notes=payload.notes,
        )
    except service.ValidationProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except AccessDenied as exc:
        # A forbidden *category* is worth explaining -- unlike a forbidden
        # site, it leaks nothing and the user can act on it.
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc) or "Not allowed") from None

    # 201 only when something was actually created. A replayed idempotency key
    # is a successful no-op, and saying "created" about it would be a lie a
    # retrying client could act on.
    if not created:
        response.status_code = status.HTTP_200_OK

    return {
        "created": created,
        "id": str(expense.id),
        "amount": expense.amount,
        "category": expense.category,
        "payee": expense.payee,
    }


@router.post("/expenses/{expense_id}/void")
def void_expense(expense_id: str, payload: VoidIn, ctx: Ctx, db: Db) -> dict:
    """Take an expense out of the accounts, keeping the record."""
    try:
        parsed = uuid.UUID(expense_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    try:
        expense = service.void_expense(db, ctx, parsed, payload.reason)
    except service.ValidationProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except AccessDenied as exc:
        detail = str(exc)
        # "not yours to void" is actionable; "no such expense" must stay opaque.
        if detail and detail != "Resource not found":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail) from None
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    return {"id": str(expense.id), "status": expense.status}
