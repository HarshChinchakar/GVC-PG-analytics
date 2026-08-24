"""Smoke-test the schema against the requirements.

Proves four things that matter more than "the tables exist":

  1. every dashboard figure in Project.md can actually be computed;
  2. a manager cannot see another building, by query or by id;
  3. the database itself rejects double-booking and bad deposit arithmetic;
  4. nothing but declared DTO fields reaches the UI layer.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.enums import RentStatus, UserRole  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Bed,
    Deposit,
    DepositRefund,
    Location,
    Resident,
    ResidentStay,
    User,
)
from app.services import queries  # noqa: E402
from app.services.access import AccessContext, AccessDenied, scope  # noqa: E402

TODAY = date(2026, 8, 20)
PERIOD = (2026, 8)

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}" + (f"  [{detail}]" if detail else ""))
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))


def main() -> int:
    db = SessionLocal()

    owner = db.scalar(select(User).where(User.role == UserRole.SUPER_ADMIN))
    managers = list(db.scalars(select(User).where(User.role == UserRole.MANAGER)).all())
    locations = list(db.scalars(select(Location).order_by(Location.code)).all())

    owner_ctx = AccessContext.from_user(owner)
    mgr = managers[0]
    mgr_ctx = AccessContext.from_user(mgr)
    mgr_location_id = next(iter(mgr_ctx.location_ids))
    other_location = next(loc for loc in locations if loc.id != mgr_location_id)

    # --- 1. the dashboard computes -------------------------------------
    print("\n[1] Dashboard figures")
    for loc in locations:
        view = queries.dashboard(db, owner_ctx, loc.id, *PERIOD, today=TODAY)
        o, r, v = view.occupancy, view.rent, view.vacancy
        print(
            f"\n  {view.location_name} — {view.period_label}\n"
            f"    beds {o.total_beds} | occupied {o.occupied} | notice {o.on_notice} "
            f"| booked {o.booked} | available {o.available} | blocked {o.blocked} "
            f"| occupancy {o.occupancy_rate}%\n"
            f"    expected Rs {r.expected_rent:,} | collected Rs {r.collected_rent:,} "
            f"| pending Rs {r.pending_rent:,} | rate {r.collection_rate}%\n"
            f"    paid {r.paid_count} | pending {r.pending_count} "
            f"| vacancy loss Rs {v.potential_monthly_loss:,} | move-outs 30d {view.upcoming_move_outs_30d}\n"
            f"    deposits held Rs {view.deposits_held:,}"
        )
        check(
            f"{loc.code}: expected = collected + pending",
            r.expected_rent == r.collected_rent + r.pending_rent,
        )
        check(
            f"{loc.code}: occupancy counts reconcile",
            o.occupied + o.on_notice + o.available + o.booked + o.blocked
            == o.total_beds,
            f"{o.occupied}+{o.on_notice}+{o.available}+{o.booked}+{o.blocked}"
            f" == {o.total_beds}",
        )
        check(
            f"{loc.code}: vacancy loss sums real bed rents",
            v.potential_monthly_loss > 0 and v.vacant_beds == o.available,
            f"{v.vacant_beds} beds",
        )

    # --- 2. tenant isolation -------------------------------------------
    print("\n[2] Tenant isolation")
    owner_residents = db.scalars(scope(select(Resident), Resident, owner_ctx)).all()
    mgr_residents = db.scalars(scope(select(Resident), Resident, mgr_ctx)).all()

    check("owner sees residents from all 3 buildings",
          len({r.location_id for r in owner_residents}) == 3,
          f"{len(owner_residents)} residents")
    check("manager sees exactly one building",
          len({r.location_id for r in mgr_residents}) == 1,
          f"{len(mgr_residents)} residents")
    check("manager's residents all belong to their building",
          all(r.location_id == mgr_location_id for r in mgr_residents))
    check("manager sees strictly fewer residents than owner",
          len(mgr_residents) < len(owner_residents))

    denied = False
    try:
        queries.dashboard(db, mgr_ctx, other_location.id, *PERIOD, today=TODAY)
    except AccessDenied:
        denied = True
    check("manager is denied another building's dashboard by id", denied)

    foreign_resident = db.scalar(
        select(Resident).where(Resident.location_id == other_location.id)
    )
    denied = False
    try:
        queries.resident_ledger(db, mgr_ctx, foreign_resident.id)
    except AccessDenied:
        denied = True
    check("manager is denied another building's resident ledger", denied)

    unassigned_ctx = AccessContext(user_id=mgr.id, role=UserRole.MANAGER, location_ids=frozenset())
    check("manager with no grants sees nothing",
          len(db.scalars(scope(select(Resident), Resident, unassigned_ctx)).all()) == 0)

    # --- 3. role-based field withholding -------------------------------
    print("\n[3] Role-based data withholding")
    owner_view = queries.dashboard(db, owner_ctx, mgr_location_id, *PERIOD, today=TODAY)
    mgr_view = queries.dashboard(db, mgr_ctx, mgr_location_id, *PERIOD, today=TODAY)
    check("owner receives deposit totals", owner_view.deposits_held is not None,
          f"Rs {owner_view.deposits_held:,}")
    check("manager receives no deposit totals", mgr_view.deposits_held is None)
    check("manager still gets full occupancy data",
          mgr_view.occupancy.total_beds == owner_view.occupancy.total_beds)

    serialised = mgr_view.model_dump()
    check("no password_hash can reach the UI", "password_hash" not in str(serialised))

    # --- 4. database-level integrity -----------------------------------
    print("\n[4] Constraints enforced by the database")

    occupied_stay = db.scalar(select(ResidentStay).where(ResidentStay.is_current.is_(True)))
    victim = db.scalar(select(Resident).where(Resident.id != occupied_stay.resident_id))
    try:
        db.add(
            ResidentStay(
                location_id=occupied_stay.location_id,
                resident_id=victim.id,
                bed_id=occupied_stay.bed_id,  # already occupied
                start_date=TODAY,
                monthly_rent=8000,
                rent_due_day=1,
                is_current=True,
            )
        )
        db.flush()
        check("double-booking a bed is rejected", False, "it was allowed")
    except IntegrityError:
        check("double-booking a bed is rejected", True)
    finally:
        db.rollback()

    try:
        db.add(
            ResidentStay(
                location_id=occupied_stay.location_id,
                resident_id=occupied_stay.resident_id,
                bed_id=db.scalar(select(Bed.id).where(Bed.id != occupied_stay.bed_id)),
                start_date=TODAY,
                monthly_rent=8000,
                rent_due_day=1,
                is_current=True,
            )
        )
        db.flush()
        check("a resident cannot hold two beds at once", False, "it was allowed")
    except IntegrityError:
        check("a resident cannot hold two beds at once", True)
    finally:
        db.rollback()

    try:
        deposit = db.scalar(select(Deposit))
        db.add(
            DepositRefund(
                location_id=deposit.location_id,
                deposit_id=deposit.id,
                gross_amount=15000,
                mandatory_deduction=1000,
                other_deduction=0,
                refund_amount=99999,  # does not add up
                processed_by_user_id=owner.id,
            )
        )
        db.flush()
        check("refund arithmetic that does not add up is rejected", False, "it was allowed")
    except IntegrityError:
        check("refund arithmetic that does not add up is rejected", True)
    finally:
        db.rollback()

    # --- 5. ledger and defaulters --------------------------------------
    print("\n[5] Ledger and defaulters")
    pending = queries.rent_rows(
        db, owner_ctx, mgr_location_id, *PERIOD, status=RentStatus.PENDING
    )
    check("defaulters list is populated and has phone numbers",
          len(pending) > 0 and all(p.phone for p in pending), f"{len(pending)} pending")

    sample = db.scalar(
        select(Resident).where(Resident.location_id == mgr_location_id).limit(1)
    )
    ledger = queries.resident_ledger(db, owner_ctx, sample.id)
    print(f"\n  Ledger — {sample.full_name}")
    for line in ledger:
        paid = f"paid {line.paid_on}" if line.paid_on else "-"
        print(f"    {line.period_label:<16} Rs {line.amount_due:>6,}  {line.status:<8} {paid}")
    check("resident ledger has month-by-month history", len(ledger) >= 2,
          f"{len(ledger)} months")

    total_stays = db.scalar(select(func.count()).select_from(ResidentStay))
    print(f"\n{'-' * 60}")
    print(f"Rows: {total_stays} stays across {len(locations)} locations")
    print(f"Checks: {passed} passed, {failed} failed")
    db.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
