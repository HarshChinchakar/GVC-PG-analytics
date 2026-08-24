"""Independent verification of every dashboard figure.

The dashboard numbers come from SQL aggregates. This script recomputes each one
by a DIFFERENT route -- pulling raw rows and totalling them in Python -- and
asserts the two agree exactly. An aggregate and a hand count that disagree mean
a bug in one of them; agreeing on every building and every month means the
figure is trustworthy.

It also checks the internal identities that must hold no matter what the data
looks like (expected = collected + pending, bed counts sum to the total, and so
on), and hunts for data states that would silently corrupt a figure.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.enums import (  # noqa: E402
    BedStatus, DepositStatus, NoticeStatus, RentStatus, ResidentStatus, UserRole,
)
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Bed, Deposit, DepositRefund, Location, MoveOutNotice, Payment,
    RentRecord, Resident, ResidentStay, User,
)
from app.services import queries  # noqa: E402
from app.services.access import AccessContext  # noqa: E402

TODAY = date(2026, 8, 20)
ok = bad = 0


def eq(label: str, a, b, extra: str = "") -> None:
    global ok, bad
    if a == b:
        ok += 1
        print(f"  OK    {label:<52} {a}{'  ' + extra if extra else ''}")
    else:
        bad += 1
        print(f"  WRONG {label:<52} aggregate={a}  recomputed={b}  {extra}")


def main() -> int:
    db = SessionLocal()
    owner = db.scalar(select(User).where(User.role == UserRole.SUPER_ADMIN))
    ctx = AccessContext.from_user(owner)
    locations = db.scalars(select(Location).order_by(Location.code)).all()

    for loc in locations:
        print(f"\n=== {loc.name} ({loc.code}) " + "=" * (46 - len(loc.name)))

        # ---- occupancy: aggregate vs row-by-row count -----------------
        agg = queries.occupancy_stats(db, ctx, loc.id)
        beds = db.scalars(
            select(Bed).where(Bed.location_id == loc.id, Bed.is_active.is_(True))
        ).all()
        manual = defaultdict(int)
        for b in beds:
            manual[b.status] += 1

        eq("beds: occupied", agg.occupied, manual[BedStatus.OCCUPIED])
        eq("beds: on notice", agg.on_notice, manual[BedStatus.NOTICE])
        eq("beds: available", agg.available, manual[BedStatus.AVAILABLE])
        eq("beds: booked", agg.booked, manual[BedStatus.BOOKED])
        eq("beds: blocked", agg.blocked, manual[BedStatus.BLOCKED])
        eq("beds: total", agg.total_beds, len(beds))
        eq(
            "bed statuses partition the total",
            manual[BedStatus.OCCUPIED] + manual[BedStatus.NOTICE]
            + manual[BedStatus.AVAILABLE] + manual[BedStatus.BOOKED]
            + manual[BedStatus.BLOCKED],
            len(beds),
        )

        rentable = len(beds) - manual[BedStatus.BLOCKED]
        filled = manual[BedStatus.OCCUPIED] + manual[BedStatus.NOTICE]
        eq("occupancy %", agg.occupancy_rate, round(filled / rentable * 100, 1))

        # ---- bed status must match reality in resident_stays ----------
        current = db.scalars(
            select(ResidentStay).where(
                ResidentStay.location_id == loc.id, ResidentStay.is_current.is_(True)
            )
        ).all()
        occupied_bed_ids = {s.bed_id for s in current}
        flagged = {b.id for b in beds if b.status in (BedStatus.OCCUPIED, BedStatus.NOTICE)}
        eq("bed status cache matches live stays", flagged, occupied_bed_ids,
           "(cache vs resident_stays)")

        # ---- vacancy loss: aggregate vs summed bed rents --------------
        # Booked beds are excluded: someone is arriving, so that revenue is
        # committed rather than lost.
        vac = queries.vacancy_stats(db, ctx, loc.id)
        manual_loss = sum(b.default_rent for b in beds if b.status == BedStatus.AVAILABLE)
        eq("vacancy: bed count", vac.vacant_beds, manual[BedStatus.AVAILABLE])
        eq("vacancy: potential loss", vac.potential_monthly_loss, manual_loss)

        # ---- rent, for EVERY month with data --------------------------
        for year, month in queries.available_periods(db, ctx, loc.id):
            s = queries.rent_summary(db, ctx, loc.id, year, month)
            rows = db.scalars(
                select(RentRecord).where(
                    RentRecord.location_id == loc.id,
                    RentRecord.period_year == year,
                    RentRecord.period_month == month,
                )
            ).all()
            tag = f"{year}-{month:02d}"
            m_expected = sum(r.amount_due for r in rows if r.status != RentStatus.WAIVED)
            m_collected = sum(r.amount_due for r in rows if r.status == RentStatus.PAID)
            m_paid = sum(1 for r in rows if r.status == RentStatus.PAID)
            m_pending = sum(1 for r in rows if r.status == RentStatus.PENDING)

            eq(f"rent {tag}: expected", s.expected_rent, m_expected)
            eq(f"rent {tag}: collected", s.collected_rent, m_collected)
            eq(f"rent {tag}: pending", s.pending_rent, m_expected - m_collected)
            eq(f"rent {tag}: paid count", s.paid_count, m_paid)
            eq(f"rent {tag}: pending count", s.pending_count, m_pending)
            eq(f"rent {tag}: identity exp=col+pend",
               s.expected_rent, s.collected_rent + s.pending_rent)
            eq(f"rent {tag}: every record counted",
               s.paid_count + s.pending_count,
               len([r for r in rows if r.status != RentStatus.WAIVED]))

            # Collected rent must equal the money actually recorded.
            paid_ids = {r.id for r in rows if r.status == RentStatus.PAID}
            payments = db.scalars(
                select(Payment).where(Payment.rent_record_id.in_(paid_ids))
            ).all() if paid_ids else []
            eq(f"rent {tag}: payment rows match paid", len(payments), len(paid_ids))
            eq(f"rent {tag}: payment sum = collected",
               sum(p.amount for p in payments), m_collected)

            # A PAID record with no payment row, or a PENDING one with a
            # payment row, would make the tally lie.
            orphan_paid = [
                r for r in rows
                if r.status == RentStatus.PAID
                and not db.scalar(select(Payment).where(Payment.rent_record_id == r.id))
            ]
            eq(f"rent {tag}: no paid-without-payment", len(orphan_paid), 0)
            ghost = [
                r for r in rows
                if r.status == RentStatus.PENDING
                and db.scalar(select(Payment).where(Payment.rent_record_id == r.id))
            ]
            eq(f"rent {tag}: no pending-with-payment", len(ghost), 0)

        # ---- defaulters list must match the pending count -------------
        cur = queries.rent_summary(db, ctx, loc.id, TODAY.year, TODAY.month)
        pending_rows = queries.rent_rows(
            db, ctx, loc.id, TODAY.year, TODAY.month, status=RentStatus.PENDING
        )
        eq("defaulters list length = pending count",
           len(pending_rows), cur.pending_count)
        eq("defaulters list sum = pending rent",
           sum(r.amount_due for r in pending_rows), cur.pending_rent)
        eq("every defaulter has a phone number",
           sum(1 for r in pending_rows if r.phone and r.phone.strip()),
           len(pending_rows))

        # ---- deposits --------------------------------------------------
        held, refunded, unpaid = queries.deposit_totals(db, ctx, loc.id)
        deposits = db.scalars(select(Deposit).where(Deposit.location_id == loc.id)).all()
        eq("deposits held", held,
           sum(d.amount for d in deposits if d.status == DepositStatus.HELD))

        refunds = db.scalars(
            select(DepositRefund).where(DepositRefund.location_id == loc.id)
        ).all()
        eq("deposit refunds paid out", refunded,
           sum(r.refund_amount for r in refunds if r.refunded_on is not None))
        eq("refund arithmetic holds for every row",
           sum(1 for r in refunds
               if r.refund_amount == r.gross_amount - r.mandatory_deduction - r.other_deduction),
           len(refunds))
        eq("every refunded deposit is marked refunded",
           sum(1 for d in deposits if d.status == DepositStatus.REFUNDED),
           len(refunds))

        # ---- residents vs beds ----------------------------------------
        counts = queries.resident_counts(db, ctx, loc.id)
        residents = db.scalars(select(Resident).where(Resident.location_id == loc.id)).all()
        eq("residents active", counts["active"],
           sum(1 for r in residents if r.status == ResidentStatus.ACTIVE))
        eq("residents on notice", counts["notice"],
           sum(1 for r in residents if r.status == ResidentStatus.NOTICE))
        eq("residents left", counts["left"],
           sum(1 for r in residents if r.status == ResidentStatus.LEFT))
        eq("living residents = filled beds", counts["living_here"], filled)
        eq("living residents = current stays", counts["living_here"], len(current))

        # ---- move-outs -------------------------------------------------
        upcoming = queries.upcoming_move_outs(db, ctx, loc.id, today=TODAY)
        notices = db.scalars(
            select(MoveOutNotice).where(
                MoveOutNotice.location_id == loc.id,
                MoveOutNotice.status == NoticeStatus.ACTIVE,
            )
        ).all()
        eq("upcoming move-outs (30d)", len(upcoming),
           len([n for n in notices if (n.expected_move_out_date - TODAY).days <= 30]))
        eq("beds on notice = active notices", manual[BedStatus.NOTICE], len(notices))
        eq("notice period is one month for all",
           sum(1 for n in notices
               if (n.expected_move_out_date - n.notice_date).days == loc.notice_period_days),
           len(notices))

        freeing = queries.beds_freeing_soon(db, ctx, loc.id)
        eq("freeing-soon list = beds on notice", len(freeing), manual[BedStatus.NOTICE])

        # ---- vacant list -----------------------------------------------
        vacant_list = queries.vacant_beds(db, ctx, loc.id)
        eq("vacant list length = available beds", len(vacant_list), manual[BedStatus.AVAILABLE])
        eq(
            "no booked bed is offered as vacant",
            sum(1 for b in vacant_list if b.status == BedStatus.BOOKED), 0,
        )
        eq("vacant list rent sum = potential loss",
           sum(b.default_rent for b in vacant_list), manual_loss)
        eq("no blocked bed appears as vacant",
           sum(1 for b in vacant_list if b.status == BedStatus.BLOCKED), 0)

    # ---- global integrity ---------------------------------------------
    print("\n=== Reservations and vehicles " + "=" * 30)
    from app.models import BedReservation, Vehicle
    from app.core.enums import ReservationStatus

    held = db.scalars(
        select(BedReservation).where(BedReservation.status == ReservationStatus.HELD)
    ).all()
    booked_beds = db.scalars(select(Bed).where(Bed.status == BedStatus.BOOKED)).all()
    eq("every held reservation has a BOOKED bed", len(held), len(booked_beds))
    eq(
        "held reservations point at beds marked booked",
        sum(1 for r in held if db.get(Bed, r.bed_id).status == BedStatus.BOOKED),
        len(held),
    )
    eq("one held reservation per bed", len({r.bed_id for r in held}), len(held))
    eq(
        "no reservation on an occupied bed",
        sum(1 for r in held if db.get(Bed, r.bed_id).status
            in (BedStatus.OCCUPIED, BedStatus.NOTICE)),
        0,
    )
    eq(
        "every reservation is for a future arrival",
        sum(1 for r in held if r.expected_move_in >= TODAY), len(held),
    )

    vehicles = db.scalars(select(Vehicle)).all()
    eq(
        "vehicle plates are normalised consistently",
        sum(1 for v in vehicles
            if v.number_normalised == v.number_normalised.upper()
            and v.number_normalised.isalnum()),
        len(vehicles),
    )
    eq(
        "no duplicate plate within a location",
        len({(v.location_id, v.number_normalised) for v in vehicles}), len(vehicles),
    )
    eq(
        "every vehicle belongs to a resident of the same location",
        sum(1 for v in vehicles
            if db.get(Resident, v.resident_id).location_id == v.location_id),
        len(vehicles),
    )

    print("\n=== Cross-location integrity " + "=" * 31)
    all_stays = db.scalars(select(ResidentStay).where(ResidentStay.is_current.is_(True))).all()
    eq("no bed holds two current residents",
       len({s.bed_id for s in all_stays}), len(all_stays))
    eq("no resident holds two current beds",
       len({s.resident_id for s in all_stays}), len(all_stays))

    mismatched = db.execute(
        select(Bed.id).join(ResidentStay, ResidentStay.bed_id == Bed.id)
        .where(ResidentStay.location_id != Bed.location_id)
    ).all()
    eq("no stay crosses a location boundary", len(mismatched), 0)

    mixed = db.execute(
        select(RentRecord.id).join(Resident, Resident.id == RentRecord.resident_id)
        .where(RentRecord.location_id != Resident.location_id)
    ).all()
    eq("no rent record crosses a location boundary", len(mixed), 0)

    # A resident billed for a month after they moved out inflates revenue with
    # rent nobody owes. This was a real seed bug; the check stays permanently.
    over_billed = []
    for rec in db.scalars(select(RentRecord)).all():
        stay = db.get(ResidentStay, rec.stay_id)
        if stay.end_date and stay.end_date < date(rec.period_year, rec.period_month, 1):
            over_billed.append(rec.id)
    eq("no rent billed for months after a resident left", len(over_billed), 0)

    # The mirror: a stay must be billed for every month it actually covered.
    eq("every current stay has a rent record this month",
       sum(1 for s in all_stays
           if db.scalar(select(RentRecord).where(
               RentRecord.stay_id == s.id,
               RentRecord.period_year == TODAY.year,
               RentRecord.period_month == TODAY.month))),
       len(all_stays))

    print("\n" + "-" * 72)
    print(f"{ok} checks agreed, {bad} disagreed")
    db.close()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
