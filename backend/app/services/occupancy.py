"""The seat-map board, and the vehicle register.

The board answers one question per bed — what is going on with it right now —
in a single snapshot, laid out the way the building actually is:

    Floor -> Flat -> Room (a price tier) -> Bed (a seat)

Deliberately narrow. Head-counts, occupancy percentages, vacancy loss and the
list of upcoming move-outs all live on the dashboard already; repeating them
here would be clutter. What this module adds is the things only a spatial view
can give: which bed, next to which other beds, in which tier, and free from
when.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.enums import BedStatus, RentStatus, ReservationStatus
from app.models import (
    Bed,
    BedReservation,
    Flat,
    Floor,
    Location,
    MoveOutNotice,
    Payment,
    RentRecord,
    Resident,
    ResidentStay,
    Room,
    Vehicle,
    normalise_plate,
)
from app.services.access import AccessContext, AccessDenied

#: What a seat can be showing. Richer than `beds.status` because the two
#: occupied cases are the ones staff most need to tell apart at a glance:
#: someone living here who has paid, and someone living here who has not.
SEAT_OCCUPIED_PAID = "occupied_paid"
SEAT_OCCUPIED_UNPAID = "occupied_unpaid"
SEAT_NOTICE = "notice"
SEAT_BOOKED = "booked"
SEAT_VACANT = "vacant"
SEAT_BLOCKED = "blocked"

#: Tier a bed belongs to. A room *is* a price tier, so this is derived rather
#: than stored: hall beds are cheapest, attached-bath beds the premium.
TIER_HALL = "hall"
TIER_SHARED = "shared_bath"
TIER_ATTACHED = "attached_bath"

TIER_LABEL = {
    TIER_HALL: "Hall",
    TIER_SHARED: "Shared bath",
    TIER_ATTACHED: "Attached bath",
}
TIER_ORDER = [TIER_HALL, TIER_SHARED, TIER_ATTACHED]


def _tier(room_kind: str, is_attached: bool) -> str:
    if room_kind == "hall":
        return TIER_HALL
    return TIER_ATTACHED if is_attached else TIER_SHARED


def occupancy_board(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    year: int,
    month: int,
    *,
    today: date | None = None,
) -> dict:
    """Every bed in one building, arranged as it sits in the building.

    One query per concern, assembled in Python, so the whole board is a single
    consistent snapshot. Splitting it per floor would let two floors disagree
    about the same resident mid-scroll.
    """
    ctx.require(location_id)
    today = today or date.today()

    location = db.get(Location, location_id)
    if location is None:
        raise AccessDenied()

    # --- 1. every bed, with its occupant and this month's rent -----------
    rows = db.execute(
        select(
            Floor.floor_number, Floor.name,
            Flat.id, Flat.flat_number, Flat.flat_type, Flat.gender_policy,
            Room.id, Room.name, Room.room_kind, Room.is_attached,
            Bed.id, Bed.label, Bed.bed_number, Bed.status, Bed.default_rent, Bed.notes,
            Resident.id, Resident.full_name, Resident.phone, Resident.gender,
            Resident.joined_on,
            ResidentStay.monthly_rent,
            RentRecord.status, Payment.paid_on,
            MoveOutNotice.expected_move_out_date,
        )
        .join(Room, Room.id == Bed.room_id)
        .join(Flat, Flat.id == Room.flat_id)
        .join(Floor, Floor.id == Flat.floor_id)
        .outerjoin(
            ResidentStay,
            and_(ResidentStay.bed_id == Bed.id, ResidentStay.is_current.is_(True)),
        )
        .outerjoin(Resident, Resident.id == ResidentStay.resident_id)
        .outerjoin(
            RentRecord,
            and_(
                RentRecord.stay_id == ResidentStay.id,
                RentRecord.period_year == year,
                RentRecord.period_month == month,
            ),
        )
        .outerjoin(Payment, Payment.rent_record_id == RentRecord.id)
        .outerjoin(
            MoveOutNotice,
            and_(
                MoveOutNotice.stay_id == ResidentStay.id,
                MoveOutNotice.status == "active",
            ),
        )
        .where(Bed.location_id == location_id, Bed.is_active.is_(True))
        .order_by(Floor.floor_number, Flat.flat_number, Room.sort_order, Bed.bed_number)
    ).all()

    # --- 2. live bookings, keyed by bed ----------------------------------
    reservations = {
        r.bed_id: r
        for r in db.scalars(
            select(BedReservation).where(
                BedReservation.location_id == location_id,
                BedReservation.status == ReservationStatus.HELD,
            )
        ).all()
    }

    # --- 3. vehicles, keyed by resident ----------------------------------
    vehicles_by_resident: dict[uuid.UUID, list[dict]] = {}
    for v in db.scalars(
        select(Vehicle).where(
            Vehicle.location_id == location_id, Vehicle.is_active.is_(True)
        )
    ).all():
        vehicles_by_resident.setdefault(v.resident_id, []).append(
            {
                "number": v.vehicle_number,
                "type": v.vehicle_type,
                "make_model": v.make_model,
                "colour": v.colour,
            }
        )

    # --- 4. assemble ------------------------------------------------------
    floors: list[dict] = []
    tier_totals: dict[str, dict[str, int]] = {
        t: {"beds": 0, "vacant": 0, "occupied": 0} for t in TIER_ORDER
    }
    gender_totals: dict[str, dict[str, int]] = {}
    seat_totals: dict[str, int] = {}

    for row in rows:
        (floor_number, floor_name,
         flat_id, flat_number, flat_type, gender_policy,
         room_id, room_name, room_kind, is_attached,
         bed_id, bed_label, bed_number, bed_status, default_rent, bed_notes,
         resident_id, resident_name, phone, resident_gender, joined_on,
         monthly_rent, rent_status, paid_on, free_from) = row

        # -- work out what the seat should show
        reservation = reservations.get(bed_id)
        if bed_status == BedStatus.BLOCKED:
            seat = SEAT_BLOCKED
        elif bed_status == BedStatus.BOOKED or reservation is not None:
            seat = SEAT_BOOKED
        elif resident_id is None:
            seat = SEAT_VACANT
        elif free_from is not None:
            seat = SEAT_NOTICE
        elif rent_status == RentStatus.PAID or rent_status == RentStatus.WAIVED:
            seat = SEAT_OCCUPIED_PAID
        elif rent_status == RentStatus.PENDING:
            seat = SEAT_OCCUPIED_UNPAID
        else:
            # Occupied but with no bill for this month -- normally someone who
            # moved in after billing ran. Treat as settled rather than owing.
            seat = SEAT_OCCUPIED_PAID

        tier = _tier(room_kind, is_attached)

        bed_payload = {
            "id": str(bed_id),
            "label": bed_label,
            "number": bed_number,
            "seat_state": seat,
            "tier": tier,
            "rent": default_rent,
            "notes": bed_notes,
            "resident": None,
            "reservation": None,
        }

        if resident_id is not None:
            bed_payload["resident"] = {
                "id": str(resident_id),
                "name": resident_name,
                "phone": phone,
                "gender": resident_gender,
                "joined_on": joined_on.isoformat() if joined_on else None,
                "monthly_rent": monthly_rent,
                "rent_status": rent_status,
                "paid_on": paid_on.isoformat() if paid_on else None,
                "free_from": free_from.isoformat() if free_from else None,
                "vehicles": vehicles_by_resident.get(resident_id, []),
            }
        elif reservation is not None:
            bed_payload["reservation"] = {
                "person_name": reservation.person_name,
                "phone": reservation.phone,
                "expected_move_in": reservation.expected_move_in.isoformat(),
                "days_away": (reservation.expected_move_in - today).days,
                "token_amount": reservation.token_amount,
                "agreed_rent": reservation.agreed_rent,
            }

        # -- running tallies for the header rail
        seat_totals[seat] = seat_totals.get(seat, 0) + 1
        tier_totals[tier]["beds"] += 1
        if seat == SEAT_VACANT:
            tier_totals[tier]["vacant"] += 1
        elif seat in (SEAT_OCCUPIED_PAID, SEAT_OCCUPIED_UNPAID, SEAT_NOTICE):
            tier_totals[tier]["occupied"] += 1

        g = gender_totals.setdefault(
            gender_policy, {"beds": 0, "vacant": 0, "occupied": 0}
        )
        g["beds"] += 1
        if seat == SEAT_VACANT:
            g["vacant"] += 1
        elif seat in (SEAT_OCCUPIED_PAID, SEAT_OCCUPIED_UNPAID, SEAT_NOTICE):
            g["occupied"] += 1

        # -- slot it into floor / flat / tier
        if not floors or floors[-1]["number"] != floor_number:
            floors.append(
                {"number": floor_number, "name": floor_name, "flats": []}
            )
        floor = floors[-1]

        if not floor["flats"] or floor["flats"][-1]["id"] != str(flat_id):
            floor["flats"].append(
                {
                    "id": str(flat_id),
                    "flat_number": flat_number,
                    "flat_type": flat_type,
                    "gender_policy": gender_policy,
                    "tiers": [],
                }
            )
        flat = floor["flats"][-1]

        if not flat["tiers"] or flat["tiers"][-1]["room_id"] != str(room_id):
            flat["tiers"].append(
                {
                    "room_id": str(room_id),
                    "room_name": room_name,
                    "tier": tier,
                    "tier_label": TIER_LABEL[tier],
                    "rent": default_rent,
                    "beds": [],
                }
            )
        flat["tiers"][-1]["beds"].append(bed_payload)

    # Per-flat headline: filled out of rentable.
    for floor in floors:
        for flat in floor["flats"]:
            beds = [b for t in flat["tiers"] for b in t["beds"]]
            rentable = [b for b in beds if b["seat_state"] != SEAT_BLOCKED]
            filled = [
                b for b in rentable
                if b["seat_state"] in (SEAT_OCCUPIED_PAID, SEAT_OCCUPIED_UNPAID, SEAT_NOTICE)
            ]
            flat["bed_count"] = len(beds)
            flat["rentable"] = len(rentable)
            flat["filled"] = len(filled)
            flat["vacant"] = sum(1 for b in rentable if b["seat_state"] == SEAT_VACANT)

    return {
        "location_id": str(location.id),
        "location_name": location.name,
        "location_code": location.code,
        "period_year": year,
        "period_month": month,
        "period_label": date(year, month, 1).strftime("%B %Y"),
        "floors": floors,
        "seat_totals": seat_totals,
        "tiers": [
            {
                "tier": t,
                "label": TIER_LABEL[t],
                **tier_totals[t],
            }
            for t in TIER_ORDER
            if tier_totals[t]["beds"] > 0
        ],
        "gender": [
            {"policy": k, **v} for k, v in sorted(gender_totals.items())
        ],
        "generated_at": today.isoformat(),
    }


# --- vehicles -----------------------------------------------------------


def search_vehicles(
    db: Session,
    ctx: AccessContext,
    location_id: uuid.UUID,
    query: str | None = None,
    *,
    limit: int = 60,
) -> list[dict]:
    """Find a vehicle, and therefore its owner.

    Built for the question asked at the gate: whose is this? The search is run
    against the normalised plate, so "mh12 ab 4472", "MH12AB4472" and a
    remembered "4472" all reach the same row -- people rarely recall a whole
    registration.

    Residents who have already left are included on purpose: an unfamiliar
    vehicle in the compound most often belongs to someone who moved out and
    never collected it. Their status is returned so the answer is not
    misleading.
    """
    ctx.require(location_id)

    stmt = (
        select(
            Vehicle.vehicle_number, Vehicle.vehicle_type, Vehicle.make_model,
            Vehicle.colour, Vehicle.notes,
            Resident.id, Resident.full_name, Resident.phone, Resident.status,
            Bed.label, Flat.flat_number, Floor.name,
        )
        .join(Resident, Resident.id == Vehicle.resident_id)
        .outerjoin(
            ResidentStay,
            and_(
                ResidentStay.resident_id == Resident.id,
                ResidentStay.is_current.is_(True),
            ),
        )
        .outerjoin(Bed, Bed.id == ResidentStay.bed_id)
        .outerjoin(Room, Room.id == Bed.room_id)
        .outerjoin(Flat, Flat.id == Room.flat_id)
        .outerjoin(Floor, Floor.id == Flat.floor_id)
        .where(Vehicle.location_id == location_id, Vehicle.is_active.is_(True))
    )

    normalised = normalise_plate(query or "")
    if normalised:
        stmt = stmt.where(
            or_(
                Vehicle.number_normalised.contains(normalised),
                Resident.full_name.ilike(f"%{query.strip()}%"),
                Resident.phone.contains(query.strip()),
            )
        )

    stmt = stmt.order_by(Resident.full_name).limit(limit)

    return [
        {
            "vehicle_number": r[0],
            "vehicle_type": r[1],
            "make_model": r[2],
            "colour": r[3],
            "notes": r[4],
            "resident_id": str(r[5]),
            "resident_name": r[6],
            "phone": r[7],
            "resident_status": r[8],
            "bed_label": r[9],
            "flat_number": r[10],
            "floor_name": r[11],
        }
        for r in db.execute(stmt).all()
    ]
