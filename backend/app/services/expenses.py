"""Recording money out.

The first write path in the application, so it carries the rules the read
paths never needed:

  * **Idempotency.** Every create supplies a key. A repeated key returns the
    row that already exists instead of booking the spend twice. Double-tapped
    Save buttons and retried requests on a bad connection are normal, and
    neither should cost the business a second payment.
  * **Category permission.** A manager runs the building; the lease, the
    payroll and the tax bill are the owner's to file. Enforced here, not in
    the form, because a form is a suggestion.
  * **Void, never delete.** A wrong figure keeps its row, gains a reason and
    an author, and stops counting. Spend that disappears is worse than spend
    that is visibly wrong.
  * **Derived fields set in exactly one place.** `period_year`/`period_month`
    come from `expense_date` through `period_of()` and nowhere else, so they
    cannot drift apart.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import (
    CATEGORY_META,
    OWNER_ONLY_CATEGORIES,
    AuditAction,
    ExpenseCategory,
    ExpenseStatus,
    PaidFrom,
    PaymentMethod,
)
from app.core.types import utcnow
from app.models import AuditLog, Expense, ExpenseTemplate, Location, User
from app.services.access import AccessContext, AccessDenied


#: How long a manager keeps the ability to undo their own entry.
MANAGER_VOID_WINDOW = timedelta(hours=24)


class ValidationProblem(Exception):
    """A request the caller can fix by changing what they sent."""


def period_of(when: date) -> tuple[int, int]:
    """The accounting month an expense belongs to.

    The single source of `period_year`/`period_month`. Anything that writes an
    expense goes through here, so the stored period can never disagree with
    the date it came from.
    """
    return when.year, when.month


def _may_use_category(ctx: AccessContext, category: str) -> None:
    if category in OWNER_ONLY_CATEGORIES and not ctx.is_super_admin:
        raise AccessDenied(
            f"{CATEGORY_META[category]['label']} can only be filed by an owner"
        )


def options(ctx: AccessContext) -> dict:
    """What the form is allowed to offer this user.

    Served from the same constants the validator uses, so the dropdown and the
    database can never disagree about what a valid category is.
    """
    categories = [
        {
            "value": c.value,
            "label": CATEGORY_META[c]["label"],
            "group": CATEGORY_META[c]["group"],
            "recurring": CATEGORY_META[c]["recurring"],
            "owner_only": c in OWNER_ONLY_CATEGORIES,
            "allowed": ctx.is_super_admin or c not in OWNER_ONLY_CATEGORIES,
        }
        for c in ExpenseCategory
    ]
    return {
        "categories": categories,
        "payment_modes": [
            {"value": m.value, "label": m.value.replace("_", " ").title()}
            for m in PaymentMethod
        ],
        "paid_from": [
            {"value": PaidFrom.SITE_CASH, "label": "Site petty cash"},
            {"value": PaidFrom.BUSINESS_ACCOUNT, "label": "Business account"},
            {"value": PaidFrom.PERSONAL, "label": "Own pocket (reimburse)"},
        ],
    }


# --- writing -------------------------------------------------------------


def record_expense(
    db: Session,
    ctx: AccessContext,
    *,
    location_id: uuid.UUID,
    category: str,
    payee: str,
    amount: int,
    expense_date: date,
    payment_mode: str,
    idempotency_key: uuid.UUID,
    description: str | None = None,
    payment_reference: str | None = None,
    paid_from: str = PaidFrom.SITE_CASH,
    template_id: uuid.UUID | None = None,
    paid_by_user_id: uuid.UUID | None = None,
    notes: str | None = None,
    today: date | None = None,
) -> tuple[Expense, bool]:
    """File one expense. Returns (expense, created).

    `created` is False when the idempotency key has been seen before, in which
    case the original row comes back untouched.
    """
    today = today or date.today()
    ctx.require(location_id)

    # -- idempotency first: a replay must not even be validated twice.
    existing = db.scalar(
        select(Expense).where(Expense.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if not ctx.can_access(existing.location_id):
            raise AccessDenied()
        return existing, False

    # -- validation
    if category not in set(ExpenseCategory):
        raise ValidationProblem("Unknown category")
    _may_use_category(ctx, category)

    if payment_mode not in set(PaymentMethod):
        raise ValidationProblem("Unknown payment mode")
    if paid_from not in set(PaidFrom):
        raise ValidationProblem("Unknown source of funds")

    payee = (payee or "").strip()
    if not payee:
        raise ValidationProblem("Say who was paid")
    if amount is None or amount <= 0:
        raise ValidationProblem("Amount must be more than zero")
    if amount > 100_00_00_000:  # ₹100 crore — a typo, not a PG expense
        raise ValidationProblem("That amount looks wrong")
    if expense_date > today:
        raise ValidationProblem("An expense cannot be dated in the future")
    if expense_date < today - timedelta(days=730):
        raise ValidationProblem("That date is more than two years ago")

    if template_id is not None:
        template = db.get(ExpenseTemplate, template_id)
        if template is None or template.location_id != location_id:
            raise ValidationProblem("Unknown recurring item for this site")

    year, month = period_of(expense_date)

    expense = Expense(
        location_id=location_id,
        category=category,
        payee=payee,
        description=(description or "").strip() or None,
        amount=amount,
        expense_date=expense_date,
        period_year=year,
        period_month=month,
        payment_mode=payment_mode,
        payment_reference=(payment_reference or "").strip() or None,
        paid_from=paid_from,
        status=ExpenseStatus.RECORDED,
        paid_by_user_id=paid_by_user_id or ctx.user_id,
        recorded_by_user_id=ctx.user_id,
        template_id=template_id,
        idempotency_key=idempotency_key,
        notes=(notes or "").strip() or None,
    )
    db.add(expense)
    db.add(
        AuditLog(
            user_id=ctx.user_id,
            location_id=location_id,
            action=AuditAction.RECORD_EXPENSE,
            entity_type="expenses",
            entity_id=expense.id,
            summary=f"{CATEGORY_META[category]['label']} — {payee} — {amount}",
        )
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = str(exc.orig)
        # Two requests raced on the same key, or the same recurring item was
        # already booked for this month. Both are "already done", not errors
        # the user can act on -- so return what is already there.
        if "idempotency_key" in message:
            already = db.scalar(
                select(Expense).where(Expense.idempotency_key == idempotency_key)
            )
            if already is not None:
                return already, False
        if "uq_template_once_per_month" in message:
            raise ValidationProblem(
                "That recurring item is already recorded for this month"
            ) from exc
        raise

    db.refresh(expense)
    return expense, True


def void_expense(
    db: Session,
    ctx: AccessContext,
    expense_id: uuid.UUID,
    reason: str,
    *,
    today: date | None = None,
) -> Expense:
    """Take an expense out of the accounts without erasing it.

    An owner may void anything. A manager may void only their own entry, and
    only within 24 hours of filing it -- enough to fix a fat-fingered amount,
    not enough to quietly rewrite last month once it has been reported on.

    A rolling 24-hour window rather than "the same calendar day": a manager who
    files at 11:58pm should not lose the ability to correct it two minutes
    later, and a date comparison across a timezone boundary gets that wrong.
    """
    today = today or date.today()

    expense = db.get(Expense, expense_id)
    if expense is None or not ctx.can_access(expense.location_id):
        raise AccessDenied()

    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValidationProblem("Give a reason for voiding this")

    if expense.status == ExpenseStatus.VOID:
        return expense  # already void; nothing to do

    if not ctx.is_super_admin:
        if expense.recorded_by_user_id != ctx.user_id:
            raise AccessDenied("You can only void an expense you recorded")
        age = utcnow() - expense.created_at
        if age > MANAGER_VOID_WINDOW:
            raise ValidationProblem(
                "A manager can only void an entry within 24 hours of recording "
                "it. Ask an owner to correct older entries."
            )

    expense.status = ExpenseStatus.VOID
    expense.void_reason = reason
    expense.voided_by_user_id = ctx.user_id
    expense.voided_at = utcnow()

    db.add(
        AuditLog(
            user_id=ctx.user_id,
            location_id=expense.location_id,
            action=AuditAction.VOID_EXPENSE,
            entity_type="expenses",
            entity_id=expense.id,
            summary=f"Voided {expense.amount} to {expense.payee}: {reason}",
        )
    )
    db.commit()
    db.refresh(expense)
    return expense


# --- reading -------------------------------------------------------------


def _row(e: Expense, users: dict[uuid.UUID, str], templates: dict[uuid.UUID, str]) -> dict:
    return {
        "id": str(e.id),
        "category": e.category,
        "category_label": CATEGORY_META[e.category]["label"],
        "payee": e.payee,
        "description": e.description,
        "amount": e.amount,
        "expense_date": e.expense_date.isoformat(),
        "payment_mode": e.payment_mode,
        "payment_reference": e.payment_reference,
        "paid_from": e.paid_from,
        "reimbursed_on": e.reimbursed_on.isoformat() if e.reimbursed_on else None,
        "status": e.status,
        "void_reason": e.void_reason,
        "paid_by": users.get(e.paid_by_user_id, "—"),
        "recorded_by": users.get(e.recorded_by_user_id, "—"),
        "recorded_at": e.created_at.isoformat(),
        "template_name": templates.get(e.template_id) if e.template_id else None,
        "notes": e.notes,
    }


def month_view(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    year: int,
    month: int,
    *,
    today: date | None = None,
) -> dict:
    """Everything the expenses screen needs, from one snapshot."""
    ctx.require(location_id)
    today = today or date.today()

    location = db.get(Location, location_id)
    if location is None:
        raise AccessDenied()

    users = {u.id: u.full_name for u in db.scalars(select(User)).all()}

    rows = db.scalars(
        select(Expense)
        .where(
            Expense.location_id == location_id,
            Expense.period_year == year,
            Expense.period_month == month,
        )
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
    ).all()

    templates = db.scalars(
        select(ExpenseTemplate)
        .where(
            ExpenseTemplate.location_id == location_id,
            ExpenseTemplate.is_active.is_(True),
        )
        .order_by(ExpenseTemplate.name)
    ).all()
    template_names = {t.id: t.name for t in templates}

    live = [e for e in rows if e.status == ExpenseStatus.RECORDED]
    total = sum(e.amount for e in live)

    by_category: dict[str, dict] = {}
    for e in live:
        entry = by_category.setdefault(
            e.category,
            {
                "category": e.category,
                "label": CATEGORY_META[e.category]["label"],
                "group": CATEGORY_META[e.category]["group"],
                "amount": 0,
                "count": 0,
            },
        )
        entry["amount"] += e.amount
        entry["count"] += 1
    ranked = sorted(by_category.values(), key=lambda c: c["amount"], reverse=True)
    for c in ranked:
        c["share"] = round(c["amount"] / total * 100, 1) if total else 0.0

    # Which recurring items are still missing for this month. This is what
    # turns the screen from a log into a checklist -- an unrecorded site rent
    # is invisible on a list of what *was* paid.
    booked_template_ids = {e.template_id for e in live if e.template_id}
    due = [
        {
            "id": str(t.id),
            "name": t.name,
            "category": t.category,
            "category_label": CATEGORY_META[t.category]["label"],
            "payee": t.payee,
            "default_amount": t.default_amount,
            "payment_mode": t.payment_mode,
            "paid_from": t.paid_from,
            "day_of_month": t.day_of_month,
            "suggested_date": date(year, month, min(t.day_of_month, 28)).isoformat(),
            "allowed": ctx.is_super_admin or t.category not in OWNER_ONLY_CATEGORIES,
        }
        for t in templates
        if t.id not in booked_template_ids
    ]

    owed = sum(
        e.amount
        for e in live
        if e.paid_from == PaidFrom.PERSONAL and e.reimbursed_on is None
    )

    return {
        "location_id": str(location.id),
        "location_name": location.name,
        "location_code": location.code,
        "period_year": year,
        "period_month": month,
        "period_label": date(year, month, 1).strftime("%B %Y"),
        "total": total,
        "entry_count": len(live),
        "voided_count": len(rows) - len(live),
        "reimbursements_owed": owed,
        "by_category": ranked,
        "due_this_month": due,
        "expenses": [_row(e, users, template_names) for e in rows],
        "options": options(ctx),
        "generated_at": today.isoformat(),
    }


def trend(
    db: Session, ctx: AccessContext, location_id: uuid.UUID, months: int = 6
) -> list[dict]:
    """Total recorded spend per month, oldest first."""
    ctx.require(location_id)
    rows = db.execute(
        select(
            Expense.period_year,
            Expense.period_month,
            func.sum(Expense.amount),
            func.count(),
        )
        .where(
            Expense.location_id == location_id,
            Expense.status == ExpenseStatus.RECORDED,
        )
        .group_by(Expense.period_year, Expense.period_month)
        .order_by(Expense.period_year.desc(), Expense.period_month.desc())
        .limit(months)
    ).all()
    return [
        {
            "period": f"{y}-{m:02d}",
            "label": date(y, m, 1).strftime("%b %Y"),
            "total": int(total or 0),
            "count": int(count or 0),
        }
        for y, m, total, count in reversed(rows)
    ]
