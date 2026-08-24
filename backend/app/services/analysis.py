"""Revenue analysis for one building and one month.

The financial model
-------------------
Four money figures, in order of how much of them we actually see:

    POTENTIAL   every active bed at its own list rent, if all were let
      └─ minus vacancy loss (empty beds)
    CONTRACTED  what current residents have actually agreed to pay
      └─ minus rate leakage (beds let below list price)
    BILLED      what was invoiced for the month
      └─ minus pending (unpaid)
    COLLECTED   what came in

The headline number is **yield** = collected / potential, and it factors
exactly into three independent rates:

    yield = occupancy rate  x  rate realisation  x  collection rate
            (empty beds)      (under-billing)      (non-payment)

Those three multiply to yield exactly, by construction -- see
`Segment.rate_realisation` for why the middle term is measured against billed
rather than contracted rent.

That decomposition is the point of this screen. A yield of 78% means something
very different if it is 95 x 98 x 84 (people are not paying) than if it is
80 x 99 x 98 (beds are empty). They are three different problems with three
different fixes, and a single revenue figure hides which one you have.

How the aggregation is built
----------------------------
Two queries, one row per bed and one row per rent record, rolled up in Python
across every dimension. Deliberately *not* one SQL GROUP BY per dimension:
rolling up a single fact set guarantees that floors, flat types, genders and
bed kinds all sum to identical totals. Six separate queries with six slightly
different join paths would eventually disagree, and a report whose own
subtotals contradict each other is worse than no report.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.enums import BedStatus, RentStatus
from app.models import (
    Bed,
    Flat,
    Floor,
    Payment,
    RentRecord,
    Resident,
    ResidentStay,
    Room,
)
from app.models.location import Location
from app.services.access import AccessContext, AccessDenied

# Beds under notice are still occupied and still paying, so they count as
# filled everywhere in this module.
FILLED = (BedStatus.OCCUPIED, BedStatus.NOTICE)


def _pct(numerator: float, denominator: float) -> float:
    """Percentage, or 0.0 when there is nothing to divide by.

    Returning 0 rather than None keeps every segment the same shape, so the UI
    never has to special-case an empty floor.
    """
    return round(numerator / denominator * 100, 1) if denominator else 0.0


@dataclass
class Segment:
    """One slice of the building — a floor, a flat type, a gender, a bed kind."""

    key: str
    label: str

    beds: int = 0
    occupied: int = 0
    vacant: int = 0
    booked: int = 0
    blocked: int = 0

    potential: int = 0        # list value of every active bed
    occupied_potential: int = 0  # list value of the filled beds only
    contracted: int = 0       # agreed rent of current residents
    booked_potential: int = 0  # list value of beds reserved but not occupied
    billed: int = 0           # invoiced this month
    collected: int = 0        # received this month

    residents: int = 0
    paid_count: int = 0
    pending_count: int = 0

    #: Bed labels, so the UI can show which beds sit behind a weak segment.
    sample_beds: list[str] = field(default_factory=list)

    # -- derived ---------------------------------------------------------

    @property
    def rentable(self) -> int:
        """Beds that could be let. Blocked beds are excluded: a bed under
        repair is not a vacancy anyone can sell."""
        return self.beds - self.blocked

    @property
    def pending(self) -> int:
        return self.billed - self.collected

    @property
    def vacancy_loss(self) -> int:
        """List value of the beds that are empty AND still sellable.

        Booked beds are excluded: someone is arriving, so that money is not
        lost, merely not yet flowing. Counting it as loss would overstate the
        problem and send staff chasing beds already spoken for.
        """
        return self.potential - self.occupied_potential - self.booked_potential

    @property
    def rate_leakage(self) -> int:
        """List value of filled beds, minus what those residents actually pay.

        Positive means beds are let below list price -- discounts, legacy
        rents never revised, or a list price set too optimistically.
        """
        return self.occupied_potential - self.contracted

    @property
    def occupancy_rate(self) -> float:
        return _pct(self.occupied, self.rentable)

    @property
    def value_occupancy_rate(self) -> float:
        """Occupancy weighted by rent, not by headcount.

        A floor of cheap hall beds can be 90% full and still contribute little.
        This is the version that actually feeds yield.
        """
        return _pct(self.occupied_potential, self.potential)

    @property
    def rate_realisation(self) -> float:
        """What we invoiced, as a share of the list value of the filled beds.

        Deliberately measured against `billed` rather than `contracted`, so
        that the three factors multiply to yield **exactly**:

            (Po/P) x (B/Po) x (R/B)  ==  R/P

        Using contracted here would look more intuitive but leaves a residue:
        a resident who left mid-month is still billed for that month while no
        longer being a current contract, so contracted and billed legitimately
        differ and the factors would not reconcile. A decomposition that does
        not add up is worse than a slightly less obvious one.
        """
        return _pct(self.billed, self.occupied_potential)

    @property
    def contract_realisation(self) -> float:
        """Contracted rent as a share of the list value of the filled beds.

        The pricing view: are current residents paying list price? Shown
        alongside `rate_leakage`, and kept out of the yield decomposition for
        the reason above.
        """
        return _pct(self.contracted, self.occupied_potential)

    @property
    def collection_rate(self) -> float:
        return _pct(self.collected, self.billed)

    @property
    def yield_rate(self) -> float:
        """The headline: collected as a share of full potential."""
        return _pct(self.collected, self.potential)

    @property
    def revpab(self) -> int:
        """Revenue per available bed, including the empty ones.

        The hotel industry's RevPAR, applied to beds. It is the only per-bed
        figure that lets a 48-bed building be compared with a 32-bed one.
        """
        return round(self.collected / self.rentable) if self.rentable else 0

    @property
    def arpo(self) -> int:
        """Average revenue per occupied bed -- the realised price point."""
        return round(self.collected / self.occupied) if self.occupied else 0

    @property
    def avg_list_rent(self) -> int:
        return round(self.potential / self.beds) if self.beds else 0

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "beds": self.beds,
            "occupied": self.occupied,
            "vacant": self.vacant,
            "booked": self.booked,
            "blocked": self.blocked,
            "rentable": self.rentable,
            "residents": self.residents,
            "potential": self.potential,
            "contracted": self.contracted,
            "billed": self.billed,
            "collected": self.collected,
            "pending": self.pending,
            "vacancy_loss": self.vacancy_loss,
            "rate_leakage": self.rate_leakage,
            "occupancy_rate": self.occupancy_rate,
            "value_occupancy_rate": self.value_occupancy_rate,
            "rate_realisation": self.rate_realisation,
            "contract_realisation": self.contract_realisation,
            "collection_rate": self.collection_rate,
            "yield_rate": self.yield_rate,
            "revpab": self.revpab,
            "arpo": self.arpo,
            "avg_list_rent": self.avg_list_rent,
            "paid_count": self.paid_count,
            "pending_count": self.pending_count,
            "sample_beds": self.sample_beds[:6],
        }


class _Grouping:
    """Accumulates segments for one dimension, preserving a display order."""

    def __init__(self, name: str, title: str, question: str) -> None:
        self.name = name
        self.title = title
        self.question = question
        self._segments: dict[str, Segment] = {}
        self._order: list[str] = []

    def get(self, key: str, label: str) -> Segment:
        if key not in self._segments:
            self._segments[key] = Segment(key=key, label=label)
            self._order.append(key)
        return self._segments[key]

    def sorted_segments(self) -> list[Segment]:
        return [self._segments[k] for k in self._order]

    def as_dict(self, sort_by_yield: bool = False) -> dict:
        segments = self.sorted_segments()
        if sort_by_yield:
            segments = sorted(segments, key=lambda s: s.yield_rate, reverse=True)
        return {
            "name": self.name,
            "title": self.title,
            "question": self.question,
            "segments": [s.as_dict() for s in segments],
        }


def revenue_analysis(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    year: int,
    month: int,
) -> dict:
    """The full drill-down for one building and one month."""
    ctx.require(location_id)

    location = db.get(Location, location_id)
    if location is None:
        raise AccessDenied()

    # ---- 1. bed inventory: one row per active bed --------------------
    bed_rows = db.execute(
        select(
            Bed.id,
            Bed.label,
            Bed.status,
            Bed.default_rent,
            Room.is_attached,
            Room.room_kind,
            Room.name,
            Flat.flat_number,
            Flat.flat_type,
            Flat.gender_policy,
            Floor.floor_number,
            Floor.name,
            ResidentStay.monthly_rent,
            Resident.gender,
        )
        .join(Room, Room.id == Bed.room_id)
        .join(Flat, Flat.id == Room.flat_id)
        .join(Floor, Floor.id == Flat.floor_id)
        .outerjoin(
            ResidentStay,
            and_(ResidentStay.bed_id == Bed.id, ResidentStay.is_current.is_(True)),
        )
        .outerjoin(Resident, Resident.id == ResidentStay.resident_id)
        .where(Bed.location_id == location_id, Bed.is_active.is_(True))
        .order_by(Floor.floor_number, Flat.flat_number, Bed.bed_number)
    ).all()

    # ---- 2. rent facts: one row per rent record in the period --------
    # Joined through the stay so that a resident who left mid-month still has
    # their rent attributed to the bed they occupied.
    rent_rows = db.execute(
        select(
            ResidentStay.bed_id,
            RentRecord.amount_due,
            RentRecord.status,
            RentRecord.due_date,
            Payment.paid_on,
        )
        .join(ResidentStay, ResidentStay.id == RentRecord.stay_id)
        .outerjoin(Payment, Payment.rent_record_id == RentRecord.id)
        .where(
            RentRecord.location_id == location_id,
            RentRecord.period_year == year,
            RentRecord.period_month == month,
        )
    ).all()

    rent_by_bed: dict[uuid.UUID, list] = {}
    for bed_id, amount, status, due_date, paid_on in rent_rows:
        rent_by_bed.setdefault(bed_id, []).append((amount, status, due_date, paid_on))

    # ---- 3. dimensions ------------------------------------------------
    dimensions = {
        "floor": _Grouping(
            "floor", "By floor",
            "Which floors carry the building, and which are dead weight?",
        ),
        "flat_type": _Grouping(
            "flat_type", "By flat type",
            "Do 2BHK or 3BHK units earn more per bed?",
        ),
        "room_kind": _Grouping(
            "room_kind", "Hall vs bedroom",
            "Hall beds are cheapest -- are they worth the space?",
        ),
        "attachment": _Grouping(
            "attachment", "Attached vs non-attached",
            "Does the attached-bathroom premium actually get realised?",
        ),
        "gender": _Grouping(
            "gender", "Male vs female flats",
            "Which side of the building performs better?",
        ),
        "flat": _Grouping(
            "flat", "By flat",
            "The individual units, best to worst.",
        ),
    }

    total = Segment(key="total", label=location.name)

    FLAT_TYPE_LABEL = {
        "1bhk": "1 BHK", "2bhk": "2 BHK", "3bhk": "3 BHK",
        "rk": "RK", "other": "Other",
    }

    for row in bed_rows:
        (bed_id, bed_label, status, list_rent, is_attached, room_kind, _room_name,
         flat_number, flat_type, gender_policy, floor_number, floor_name,
         stay_rent, _resident_gender) = row

        is_filled = status in FILLED
        is_blocked = status == BedStatus.BLOCKED
        is_vacant = status == BedStatus.AVAILABLE
        is_booked = status == BedStatus.BOOKED

        facts = rent_by_bed.get(bed_id, [])
        billed = sum(a for a, s, _, _ in facts if s != RentStatus.WAIVED)
        collected = sum(a for a, s, _, _ in facts if s == RentStatus.PAID)
        paid_n = sum(1 for _, s, _, _ in facts if s == RentStatus.PAID)
        pending_n = sum(1 for _, s, _, _ in facts if s == RentStatus.PENDING)

        targets = [
            total,
            dimensions["floor"].get(f"floor-{floor_number}", floor_name),
            dimensions["flat_type"].get(flat_type, FLAT_TYPE_LABEL.get(flat_type, flat_type)),
            dimensions["room_kind"].get(room_kind, "Hall" if room_kind == "hall" else "Bedroom"),
            dimensions["attachment"].get(
                "attached" if is_attached else "non_attached",
                "Attached bath" if is_attached else "Shared bath",
            ),
            dimensions["gender"].get(gender_policy, gender_policy.title()),
            dimensions["flat"].get(f"flat-{flat_number}", f"Flat {flat_number}"),
        ]

        for seg in targets:
            seg.beds += 1
            seg.potential += list_rent
            seg.billed += billed
            seg.collected += collected
            seg.paid_count += paid_n
            seg.pending_count += pending_n

            if is_filled:
                seg.occupied += 1
                seg.residents += 1
                seg.occupied_potential += list_rent
                seg.contracted += stay_rent or 0
            elif is_blocked:
                seg.blocked += 1
            elif is_booked:
                # Empty today, but committed -- so not counted as a vacancy
                # the owner could still sell.
                seg.booked += 1
                seg.booked_potential += list_rent
            elif is_vacant:
                seg.vacant += 1
                if len(seg.sample_beds) < 6:
                    seg.sample_beds.append(bed_label)

    # ---- 4. payment behaviour -----------------------------------------
    on_time = late_week = late_fortnight = late_long = 0
    delays: list[int] = []
    for _bed_id, _amount, status, due_date, paid_on in rent_rows:
        if status != RentStatus.PAID or paid_on is None:
            continue
        delay = (paid_on - due_date).days
        delays.append(delay)
        if delay <= 0:
            on_time += 1
        elif delay <= 7:
            late_week += 1
        elif delay <= 15:
            late_fortnight += 1
        else:
            late_long += 1

    payment_behaviour = {
        "on_or_before_due": on_time,
        "within_a_week": late_week,
        "within_a_fortnight": late_fortnight,
        "over_a_fortnight": late_long,
        "average_days_late": round(sum(delays) / len(delays), 1) if delays else 0.0,
        "worst_days_late": max(delays) if delays else 0,
        "payments_counted": len(delays),
    }

    # ---- 5. month-on-month trend --------------------------------------
    trend_rows = db.execute(
        select(
            RentRecord.period_year,
            RentRecord.period_month,
            func.sum(
                func.coalesce(
                    func.nullif(RentRecord.amount_due, None), 0
                )
            ).filter(RentRecord.status != RentStatus.WAIVED),
            func.sum(RentRecord.amount_due).filter(RentRecord.status == RentStatus.PAID),
        )
        .where(RentRecord.location_id == location_id)
        .group_by(RentRecord.period_year, RentRecord.period_month)
        .order_by(RentRecord.period_year, RentRecord.period_month)
    ).all()

    trend = [
        {
            "period": f"{y}-{m:02d}",
            "label": date(y, m, 1).strftime("%b %Y"),
            "billed": int(b or 0),
            "collected": int(c or 0),
            "pending": int((b or 0) - (c or 0)),
            "collection_rate": _pct(float(c or 0), float(b or 0)),
            "yield_rate": _pct(float(c or 0), float(total.potential)),
        }
        for y, m, b, c in trend_rows
    ]

    # ---- 6. callouts ---------------------------------------------------
    def _extremes(grouping: _Grouping, minimum_beds: int = 1):
        segs = [s for s in grouping.sorted_segments() if s.rentable >= minimum_beds]
        if len(segs) < 2:
            return None, None
        ranked = sorted(segs, key=lambda s: s.yield_rate)
        return ranked[-1], ranked[0]

    best_floor, worst_floor = _extremes(dimensions["floor"])
    best_flat, worst_flat = _extremes(dimensions["flat"], minimum_beds=2)

    callouts = []
    if worst_floor and best_floor and worst_floor.key != best_floor.key:
        callouts.append({
            "kind": "floor_gap",
            "headline": f"{worst_floor.label} yields {worst_floor.yield_rate}% against {best_floor.label} at {best_floor.yield_rate}%",
            "detail": (
                f"{worst_floor.label} has {worst_floor.vacant} empty "
                f"{'bed' if worst_floor.vacant == 1 else 'beds'} costing "
                f"{worst_floor.vacancy_loss:,} a month."
            ),
        })
    if worst_flat:
        callouts.append({
            "kind": "worst_flat",
            "headline": f"{worst_flat.label} is the weakest unit at {worst_flat.yield_rate}% yield",
            "detail": (
                f"{worst_flat.occupied} of {worst_flat.rentable} beds let; "
                f"{worst_flat.vacancy_loss:,} a month sitting empty."
            ),
        })
    if total.rate_leakage > 0:
        callouts.append({
            "kind": "rate_leakage",
            "headline": f"{total.rate_leakage:,} a month in rents below list price",
            "detail": (
                f"Occupied beds are listed at {total.occupied_potential:,} but "
                f"contracted at {total.contracted:,} — "
                f"{total.rate_realisation}% of list."
            ),
        })
    elif total.rate_leakage < 0:
        callouts.append({
            "kind": "rate_premium",
            "headline": f"Occupied beds earn {abs(total.rate_leakage):,} above list price",
            "detail": "List rents on these beds are set below what residents actually pay.",
        })
    if total.pending > 0:
        callouts.append({
            "kind": "collection",
            "headline": f"{total.pending:,} uncollected from {total.pending_count} residents",
            "detail": f"Collection is running at {total.collection_rate}% for the month.",
        })

    return {
        "location_id": str(location.id),
        "location_name": location.name,
        "location_code": location.code,
        "period_year": year,
        "period_month": month,
        "period_label": date(year, month, 1).strftime("%B %Y"),

        "waterfall": {
            "potential": total.potential,
            "vacancy_loss": total.vacancy_loss,
            "contracted": total.contracted,
            "rate_leakage": total.rate_leakage,
            "billed": total.billed,
            "pending": total.pending,
            "collected": total.collected,
        },
        "factors": {
            "value_occupancy_rate": total.value_occupancy_rate,
            "rate_realisation": total.rate_realisation,
            "collection_rate": total.collection_rate,
            "yield_rate": total.yield_rate,
            "contract_realisation": total.contract_realisation,
        },
        "totals": total.as_dict(),
        "dimensions": [
            dimensions["floor"].as_dict(),
            dimensions["gender"].as_dict(),
            dimensions["attachment"].as_dict(),
            dimensions["room_kind"].as_dict(),
            dimensions["flat_type"].as_dict(),
            dimensions["flat"].as_dict(sort_by_yield=True),
        ],
        "payment_behaviour": payment_behaviour,
        "trend": trend,
        "callouts": callouts,
    }
