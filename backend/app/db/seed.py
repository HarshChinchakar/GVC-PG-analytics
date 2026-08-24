"""Realistic development data.

Builds three PGs with a believable spread of states, so every screen has
something meaningful to render and every edge case has a live example:

  * fully paid residents, and defaulters carrying two months
  * residents under notice, with beds correctly showing as NOTICE
  * residents who have already left, with settled deposits and freed beds
  * a bed blocked for repair, and a resident who moved between beds
  * three months of rent history, so the ledger screen is not empty

Deterministic: a fixed random seed means the same data every run, so a bug
found today is reproducible tomorrow.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.enums import (
    AuditAction,
    ExpenseCategory,
    ExpenseStatus,
    PaidFrom,
    ReservationStatus,
    VehicleType,
    BedStatus,
    DepositStatus,
    FlatType,
    Gender,
    GenderPolicy,
    NoticeStatus,
    PaymentMethod,
    RentStatus,
    ResidentStatus,
    RoomKind,
    UserRole,
)
from app.core.security import hash_password
from app.core.types import new_uuid, utcnow
from app.models import (
    AuditLog,
    Bed,
    Expense,
    ExpenseTemplate,
    BedReservation,
    Vehicle,
    normalise_plate,
    Deposit,
    DepositRefund,
    Flat,
    Floor,
    Location,
    MoveOutNotice,
    Payment,
    RentRecord,
    Resident,
    ResidentStay,
    Room,
    User,
    UserLocation,
)

RNG = random.Random(20260820)

# "Today" for the seed. Fixed so the data does not drift as real time passes.
TODAY = date(2026, 8, 20)

MALE_NAMES = [
    "Rahul", "Amit", "Raj", "Vikram", "Karan", "Rohit", "Sagar", "Manish",
    "Nikhil", "Aditya", "Suresh", "Arjun", "Vishal", "Gaurav", "Pranav",
    "Siddharth", "Yash", "Omkar", "Kunal", "Tejas", "Harsh", "Akash",
    "Sameer", "Ganesh", "Prasad", "Chetan", "Rakesh", "Nilesh", "Ajay",
    "Mahesh", "Sanjay", "Kiran", "Abhishek", "Mayur", "Swapnil",
]

FEMALE_NAMES = [
    "Sneha", "Priya", "Anjali", "Pooja", "Neha", "Divya", "Kavita", "Shruti",
    "Meera", "Ritu", "Swati", "Tanvi", "Isha", "Komal", "Aarti", "Snehal",
    "Rupali", "Madhuri", "Sonali", "Deepa", "Nisha", "Trupti", "Ashwini",
    "Vaishali", "Bhavna", "Shweta", "Manasi", "Rachana", "Prajakta", "Smita",
    "Ujwala", "Namrata", "Sayali", "Rohini", "Mrunal",
]

FIRST_NAMES = MALE_NAMES + FEMALE_NAMES

LAST_NAMES = [
    "Sharma", "Patil", "Deshmukh", "Kulkarni", "Joshi", "Iyer", "Nair",
    "Shah", "Gupta", "Reddy", "Jadhav", "More", "Pawar", "Bhosale", "Mehta",
    "Chavan", "Kadam", "Salunkhe", "Rane", "Naik",
]

ID_PROOFS = ["Aadhaar", "PAN", "Driving Licence", "Passport"]


def _month_label(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%B %Y")


def _recent_periods(count: int = 3) -> list[tuple[int, int]]:
    """The last `count` months ending with TODAY's month, oldest first.

    Project.md asks for roughly two months of history; we generate three so
    that "two months back" is visibly present rather than being the edge.
    """
    periods: list[tuple[int, int]] = []
    year, month = TODAY.year, TODAY.month
    for _ in range(count):
        periods.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(periods))


def _phone(used: set[str]) -> str:
    while True:
        number = f"9{RNG.randint(100000000, 999999999)}"
        if number not in used:
            used.add(number)
            return number


def _name(used: set[str], gender: str | None = None) -> str:
    """A unique full name, drawn from the pool matching the given gender."""
    pool = (
        MALE_NAMES if gender == Gender.MALE
        else FEMALE_NAMES if gender == Gender.FEMALE
        else FIRST_NAMES
    )
    for _ in range(400):
        candidate = f"{RNG.choice(pool)} {RNG.choice(LAST_NAMES)}"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError("ran out of unique names")


# --- building construction ---------------------------------------------

#: (flat_type, [(room name, kind, attached, capacity), ...])
FLAT_LAYOUTS: dict[str, list[tuple[str, str, bool, int]]] = {
    FlatType.BHK_2: [
        ("Hall", RoomKind.HALL, False, 3),
        ("Bedroom 1", RoomKind.BEDROOM, False, 2),
        ("Bedroom 2", RoomKind.BEDROOM, True, 2),
    ],
    FlatType.BHK_3: [
        ("Hall", RoomKind.HALL, False, 3),
        ("Bedroom 1", RoomKind.BEDROOM, False, 2),
        ("Bedroom 2", RoomKind.BEDROOM, True, 2),
        ("Bedroom 3", RoomKind.BEDROOM, True, 2),
    ],
    FlatType.RK: [
        ("Room", RoomKind.BEDROOM, True, 2),
    ],
}


def _build_flat(
    db: Session,
    location: Location,
    floor: Floor,
    flat_number: str,
    flat_type: str,
    base_rent: int,
    gender_policy: str,
) -> list[Bed]:
    """Create a flat with its rooms and beds, returning the beds.

    Bed labels follow the owner's convention: `<flat>-<n><A|NA>`, e.g.
    "101-1NA" is bed 1 in a non-attached room of flat 101.
    """
    flat = Flat(
        location_id=location.id,
        floor_id=floor.id,
        flat_number=flat_number,
        flat_type=flat_type,
        gender_policy=gender_policy,
    )
    db.add(flat)
    db.flush()

    beds: list[Bed] = []
    bed_counter = 0
    for order, (room_name, kind, attached, capacity) in enumerate(
        FLAT_LAYOUTS[flat_type]
    ):
        room = Room(
            location_id=location.id,
            flat_id=flat.id,
            name=room_name,
            room_kind=kind,
            is_attached=attached,
            capacity=capacity,
            sort_order=order,
        )
        db.add(room)
        db.flush()

        # An attached bed commands a premium; a hall bed is the cheapest.
        rent = base_rent + (1500 if attached else 0) - (1000 if kind == RoomKind.HALL else 0)

        for n in range(1, capacity + 1):
            bed_counter += 1
            suffix = "A" if attached else "NA"
            bed = Bed(
                location_id=location.id,
                room_id=room.id,
                bed_number=bed_counter,
                label=f"{flat_number}-{bed_counter}{suffix}",
                default_rent=rent,
                status=BedStatus.AVAILABLE,
            )
            db.add(bed)
            beds.append(bed)

    db.flush()
    return beds


def _build_location(
    db: Session,
    *,
    name: str,
    code: str,
    city: str,
    layout: list[int],
    base_rent: int,
    three_bhk: tuple[str, ...] = (),
) -> tuple[Location, list[Bed], dict]:
    """Build one building.

    `layout` is the number of flats on each floor, e.g. [2, 3, 3, 2].
    `three_bhk` names the flats that are 3BHK; everything else is a 2BHK.
    Described rather than generated, so the seed can mirror a real building.
    """
    location = Location(
        name=name,
        code=code,
        city=city,
        address_line=f"{RNG.randint(1, 90)}, {name} Road",
        contact_phone=f"020{RNG.randint(10000000, 99999999)}",
        notice_period_days=30,
        deposit_deduction=1000,
    )
    db.add(location)
    db.flush()

    all_beds: list[Bed] = []
    # bed id -> the gender policy of the flat it sits in
    bed_gender: dict = {}
    for floor_no, flats_on_floor in enumerate(layout, start=1):
        floor = Floor(
            location_id=location.id,
            floor_number=floor_no,
            name=f"Floor {floor_no}",
            sort_order=floor_no,
        )
        db.add(floor)
        db.flush()

        for index in range(flats_on_floor):
            flat_number = f"{floor_no}0{index + 1}"
            flat_type = (
                FlatType.BHK_3 if flat_number in three_bhk else FlatType.BHK_2
            )
            # Ground floors male, upper floors female -- the usual arrangement,
            # and it gives the gender revenue split something real to compare.
            policy = (
                GenderPolicy.FEMALE
                if (floor_no + index) % 3 == 0
                else GenderPolicy.MALE
            )
            beds = _build_flat(
                db, location, floor, flat_number, flat_type, base_rent, policy
            )
            for bed in beds:
                bed_gender[bed.id] = policy
            all_beds.extend(beds)

    return location, all_beds, bed_gender


# --- people -------------------------------------------------------------


def _generate_rent_history(
    db: Session,
    *,
    stay: ResidentStay,
    location: Location,
    marked_by: User,
    unpaid_months: int,
    ends_on: date | None = None,
) -> None:
    """Create one rent record per month the resident was present.

    The last `unpaid_months` months are left PENDING; everything earlier is
    marked PAID with a plausible payment date. This is what fills the ledger
    and the defaulters list.
    """
    periods = _recent_periods(3)
    billable = [
        (year, month)
        for year, month in periods
        # Bill a month only if the stay overlapped it. Both bounds matter: a
        # resident who left in June must not be billed for July, or the
        # building's revenue is overstated by rent nobody owes.
        if date(year, month, 28) >= stay.start_date
        and (ends_on is None or date(year, month, 1) <= ends_on)
    ]

    for index, (year, month) in enumerate(billable):
        months_from_end = len(billable) - index
        is_unpaid = months_from_end <= unpaid_months

        due_day = min(stay.rent_due_day, 28)
        record = RentRecord(
            location_id=location.id,
            resident_id=stay.resident_id,
            stay_id=stay.id,
            period_year=year,
            period_month=month,
            amount_due=stay.monthly_rent,
            due_date=date(year, month, due_day),
            status=RentStatus.PENDING if is_unpaid else RentStatus.PAID,
        )
        db.add(record)
        db.flush()

        if not is_unpaid:
            paid_on = date(year, month, due_day) + timedelta(days=RNG.randint(0, 6))
            db.add(
                Payment(
                    location_id=location.id,
                    rent_record_id=record.id,
                    amount=record.amount_due,
                    paid_on=min(paid_on, TODAY),
                    method=RNG.choice(
                        [PaymentMethod.UPI, PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER]
                    ),
                    marked_by_user_id=marked_by.id,
                )
            )


def _place_resident(
    db: Session,
    *,
    location: Location,
    bed: Bed,
    marked_by: User,
    used_names: set[str],
    used_phones: set[str],
    scenario: str,
    gender: str,
) -> Resident:
    """Create a resident, put them in a bed, and give them a full history.

    `scenario` decides which of the real-world states this resident lands in.
    """
    joined = TODAY - timedelta(days=RNG.randint(35, 400))
    resident = Resident(
        location_id=location.id,
        full_name=_name(used_names, gender),
        gender=gender,
        phone=_phone(used_phones),
        email=None,
        id_proof_type=RNG.choice(ID_PROOFS),
        id_proof_number=f"XXXX{RNG.randint(1000, 9999)}",
        permanent_address=f"{RNG.randint(1, 200)}, {RNG.choice(LAST_NAMES)} Nagar",
        emergency_contact_name=_name(used_names),
        emergency_contact_phone=_phone(used_phones),
        status=ResidentStatus.ACTIVE,
        joined_on=joined,
    )
    db.add(resident)
    db.flush()

    stay = ResidentStay(
        location_id=location.id,
        resident_id=resident.id,
        bed_id=bed.id,
        start_date=joined,
        monthly_rent=bed.default_rent,
        rent_due_day=min(joined.day, 28),
        is_current=True,
    )
    db.add(stay)
    db.flush()

    bed.status = BedStatus.OCCUPIED

    # Deposit: typically two months' rent, rounded to a tidy figure.
    deposit_amount = int(round(bed.default_rent * 2 / 1000.0)) * 1000
    deposit = Deposit(
        location_id=location.id,
        resident_id=resident.id,
        stay_id=stay.id,
        amount=deposit_amount,
        received_on=joined,
        method=RNG.choice([PaymentMethod.UPI, PaymentMethod.CASH]),
        status=DepositStatus.HELD,
        received_by_user_id=marked_by.id,
    )
    db.add(deposit)

    unpaid = {"paid": 0, "defaulter": 1, "long_defaulter": 2, "notice": 0, "left": 0}[
        scenario
    ]

    # For a departing resident the move-out date has to be settled first: rent
    # history is bounded by it, so it cannot be decided afterwards.
    departure: date | None = None
    notice_date: date | None = None
    if scenario == "left":
        notice_date = TODAY - timedelta(days=RNG.randint(40, 90))
        departure = notice_date + timedelta(days=location.notice_period_days)

    _generate_rent_history(
        db,
        stay=stay,
        location=location,
        marked_by=marked_by,
        unpaid_months=unpaid,
        ends_on=departure,
    )

    if scenario == "notice":
        _serve_notice(db, location=location, resident=resident, stay=stay, bed=bed, user=marked_by)
    elif scenario == "left":
        _complete_move_out(
            db,
            location=location,
            resident=resident,
            stay=stay,
            bed=bed,
            deposit=deposit,
            user=marked_by,
            notice_date=notice_date,
            left_on=departure,
        )

    return resident


def _serve_notice(
    db: Session,
    *,
    location: Location,
    resident: Resident,
    stay: ResidentStay,
    bed: Bed,
    user: User,
) -> MoveOutNotice:
    """Resident gives one month's notice; the bed becomes to-be-vacant."""
    notice_date = TODAY - timedelta(days=RNG.randint(1, 25))
    notice = MoveOutNotice(
        location_id=location.id,
        resident_id=resident.id,
        stay_id=stay.id,
        notice_date=notice_date,
        expected_move_out_date=notice_date + timedelta(days=location.notice_period_days),
        status=NoticeStatus.ACTIVE,
        reason=RNG.choice(
            ["Job relocation", "Moving closer to office", "Going back home", "Buying a flat"]
        ),
        created_by_user_id=user.id,
    )
    db.add(notice)
    resident.status = ResidentStatus.NOTICE
    bed.status = BedStatus.NOTICE
    db.add(
        AuditLog(
            user_id=user.id,
            location_id=location.id,
            action=AuditAction.SERVE_NOTICE,
            entity_type="move_out_notices",
            entity_id=notice.id,
            summary=f"{resident.full_name} served notice, leaving {notice.expected_move_out_date}",
        )
    )
    return notice


def _complete_move_out(
    db: Session,
    *,
    location: Location,
    resident: Resident,
    stay: ResidentStay,
    bed: Bed,
    deposit: Deposit,
    user: User,
    notice_date: date,
    left_on: date,
) -> None:
    """The full departure path: notice served, resident left, bed released,
    deposit settled with the mandatory deduction applied.

    The dates are passed in rather than generated here, because the rent
    history had to be bounded by the departure date before this runs.
    """

    db.add(
        MoveOutNotice(
            location_id=location.id,
            resident_id=resident.id,
            stay_id=stay.id,
            notice_date=notice_date,
            expected_move_out_date=left_on,
            actual_move_out_date=left_on,
            status=NoticeStatus.COMPLETED,
            reason="Course completed",
            created_by_user_id=user.id,
        )
    )

    resident.status = ResidentStatus.LEFT
    resident.left_on = left_on
    stay.is_current = False
    stay.end_date = left_on
    stay.end_reason = "Moved out after notice"
    bed.status = BedStatus.AVAILABLE

    other = 0 if RNG.random() < 0.7 else RNG.choice([500, 1500, 2000])
    refund = deposit.amount - location.deposit_deduction - other
    deposit.status = DepositStatus.REFUNDED
    db.add(
        DepositRefund(
            location_id=location.id,
            deposit_id=deposit.id,
            gross_amount=deposit.amount,
            mandatory_deduction=location.deposit_deduction,
            other_deduction=other,
            other_deduction_reason="Damage to furniture" if other else None,
            refund_amount=refund,
            refunded_on=left_on + timedelta(days=RNG.randint(1, 10)),
            method=PaymentMethod.BANK_TRANSFER,
            processed_by_user_id=user.id,
        )
    )
    db.add(
        AuditLog(
            user_id=user.id,
            location_id=location.id,
            action=AuditAction.RELEASE_BED,
            entity_type="beds",
            entity_id=bed.id,
            summary=f"{bed.label} released after {resident.full_name} moved out",
        )
    )


# --- vehicles and bookings ----------------------------------------------

RTO_CODES = ["MH12", "MH14", "MH01", "MH20", "KA05", "GJ01", "MP09", "UP16"]
TWO_WHEELERS = [
    ("Honda Activa", "Grey"), ("TVS Jupiter", "Blue"), ("Bajaj Pulsar", "Black"),
    ("Royal Enfield Classic", "Green"), ("Suzuki Access", "White"),
    ("Yamaha FZ", "Red"), ("Hero Splendor", "Black"), ("Ather 450X", "Grey"),
]
FOUR_WHEELERS = [
    ("Maruti Swift", "White"), ("Hyundai i20", "Red"), ("Tata Nexon", "Blue"),
    ("Honda City", "Silver"),
]


def _plate(used: set[str]) -> str:
    """A believable Indian registration, unique within the dataset."""
    while True:
        plate = (
            f"{RNG.choice(RTO_CODES)} "
            f"{RNG.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{RNG.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')} "
            f"{RNG.randint(1000, 9999)}"
        )
        if normalise_plate(plate) not in used:
            used.add(normalise_plate(plate))
            return plate


def _add_vehicles(
    db: Session, *, location: Location, resident: Resident, used_plates: set[str]
) -> None:
    """Give most residents a two-wheeler and a few a car.

    Roughly two in three, which is what a working-professional PG looks like
    and leaves enough residents without one that the lookup has to handle
    "no vehicle registered".
    """
    roll = RNG.random()
    if roll > 0.68:
        return

    make, colour = RNG.choice(TWO_WHEELERS)
    plate = _plate(used_plates)
    db.add(
        Vehicle(
            location_id=location.id,
            resident_id=resident.id,
            vehicle_number=plate,
            number_normalised=normalise_plate(plate),
            vehicle_type=VehicleType.TWO_WHEELER,
            make_model=make,
            colour=colour,
        )
    )

    # A small minority also keep a car.
    if roll < 0.08:
        make, colour = RNG.choice(FOUR_WHEELERS)
        plate = _plate(used_plates)
        db.add(
            Vehicle(
                location_id=location.id,
                resident_id=resident.id,
                vehicle_number=plate,
                number_normalised=normalise_plate(plate),
                vehicle_type=VehicleType.FOUR_WHEELER,
                make_model=make,
                colour=colour,
            )
        )


def _reserve_bed(
    db: Session,
    *,
    location: Location,
    bed: Bed,
    user: User,
    used_names: set[str],
    used_phones: set[str],
    gender: str,
) -> None:
    """Hold a vacant bed for someone arriving shortly."""
    move_in = TODAY + timedelta(days=RNG.randint(3, 28))
    db.add(
        BedReservation(
            location_id=location.id,
            bed_id=bed.id,
            person_name=_name(used_names, gender),
            phone=_phone(used_phones),
            expected_move_in=move_in,
            token_amount=RNG.choice([1000, 2000, 5000]),
            agreed_rent=bed.default_rent,
            status=ReservationStatus.HELD,
            created_by_user_id=user.id,
        )
    )
    bed.status = BedStatus.BOOKED


# --- expenses -----------------------------------------------------------

#: The costs that land every month, per building. Amounts scale with the site.
RECURRING = [
    ("Building lease",   ExpenseCategory.SITE_RENT,   "Property owner",     1.00, 5,  PaymentMethod.BANK_TRANSFER, PaidFrom.BUSINESS_ACCOUNT),
    ("Cook salary",      ExpenseCategory.SALARIES,    "Kitchen staff",      0.14, 1,  PaymentMethod.CASH,          PaidFrom.BUSINESS_ACCOUNT),
    ("Housekeeping staff", ExpenseCategory.SALARIES,  "Cleaning staff",     0.10, 1,  PaymentMethod.CASH,          PaidFrom.BUSINESS_ACCOUNT),
    ("Watchman salary",  ExpenseCategory.SECURITY,    "Night watchman",     0.08, 1,  PaymentMethod.CASH,          PaidFrom.BUSINESS_ACCOUNT),
    ("Electricity bill", ExpenseCategory.ELECTRICITY, "MSEDCL",             None, 12, PaymentMethod.UPI,           PaidFrom.BUSINESS_ACCOUNT),
    ("Water tanker",     ExpenseCategory.WATER,       "Sai Water Supply",   0.05, 8,  PaymentMethod.CASH,          PaidFrom.SITE_CASH),
    ("Broadband",        ExpenseCategory.INTERNET,    "ACT Fibernet",       0.02, 7,  PaymentMethod.UPI,           PaidFrom.BUSINESS_ACCOUNT),
    ("Cooking gas",      ExpenseCategory.GAS,         "Bharat Gas",         0.06, 15, PaymentMethod.CASH,          PaidFrom.SITE_CASH),
]

#: One-off spend a manager files during the month.
AD_HOC = [
    (ExpenseCategory.GROCERIES,    ["Reliance Fresh", "Local kirana", "D-Mart"],       1500,  9000,  "Weekly provisions"),
    (ExpenseCategory.REPAIRS,      ["Ramesh Plumbing", "Sharma Electricals", "Handyman"], 400, 6500, "Repair work"),
    (ExpenseCategory.HOUSEKEEPING, ["Cleaning supplies", "Hardware store"],             300,  2200,  "Cleaning materials"),
    (ExpenseCategory.LAUNDRY,      ["Sparkle Laundry"],                                 800,  3000,  "Bedsheet wash"),
    (ExpenseCategory.TRANSPORT,    ["Auto fare", "Porter"],                             150,   900,  "Local transport"),
    (ExpenseCategory.STAFF_WELFARE,["Staff tea & snacks"],                              200,  1200,  "Staff refreshments"),
    (ExpenseCategory.MISC,         ["Sundry"],                                          200,  2500,  "Miscellaneous"),
]


def _seed_expenses(
    db: Session,
    *,
    location: Location,
    owner: User,
    manager: User,
    monthly_rent_roll: int,
) -> None:
    """Recurring templates, plus three months of plausible spend.

    Amounts are derived from the building's rent roll so that expenses sit in
    a believable ratio to income -- roughly 55-65% of revenue, which is what a
    PG actually runs at once lease and salaries are counted.
    """
    templates: list[ExpenseTemplate] = []
    for name, category, payee, share, day, mode, source in RECURRING:
        amount = None if share is None else int(round(monthly_rent_roll * share * 0.55 / 500)) * 500
        template = ExpenseTemplate(
            location_id=location.id,
            name=name,
            category=category,
            payee=payee,
            default_amount=amount,
            payment_mode=mode,
            paid_from=source,
            day_of_month=day,
            created_by_user_id=owner.id,
        )
        db.add(template)
        templates.append(template)
    db.flush()

    for year, month in _recent_periods(3):
        is_current = (year, month) == (TODAY.year, TODAY.month)

        for template in templates:
            # The current month is deliberately left part-done, so the
            # "due this month" checklist has something in it.
            if is_current and template.category in (
                ExpenseCategory.WATER, ExpenseCategory.GAS
            ):
                continue

            amount = template.default_amount
            if amount is None:  # electricity varies with the season
                amount = int(round(monthly_rent_roll * 0.035 / 100)) * 100
                amount += RNG.randint(-1500, 2500)
            day = min(template.day_of_month, 28)
            when = date(year, month, day)
            if when > TODAY:
                continue

            db.add(
                Expense(
                    location_id=location.id,
                    category=template.category,
                    payee=template.payee,
                    description=template.name,
                    amount=max(amount, 500),
                    expense_date=when,
                    period_year=year,
                    period_month=month,
                    payment_mode=template.payment_mode,
                    paid_from=template.paid_from,
                    status=ExpenseStatus.RECORDED,
                    paid_by_user_id=owner.id,
                    recorded_by_user_id=owner.id,
                    template_id=template.id,
                    idempotency_key=new_uuid(),
                )
            )

        # Ad-hoc spend, filed by the manager who actually bought the thing.
        for _ in range(RNG.randint(5, 9)):
            category, payees, low, high, note = RNG.choice(AD_HOC)
            day = RNG.randint(1, 28)
            when = date(year, month, day)
            if when > TODAY:
                continue
            personal = RNG.random() < 0.22
            db.add(
                Expense(
                    location_id=location.id,
                    category=category,
                    payee=RNG.choice(payees),
                    description=note,
                    amount=int(round(RNG.randint(low, high) / 50)) * 50,
                    expense_date=when,
                    period_year=year,
                    period_month=month,
                    payment_mode=RNG.choice([PaymentMethod.CASH, PaymentMethod.UPI]),
                    paid_from=PaidFrom.PERSONAL if personal else PaidFrom.SITE_CASH,
                    # Older reimbursements have been settled; recent ones have not.
                    reimbursed_on=(
                        when + timedelta(days=RNG.randint(3, 12))
                        if personal and not is_current
                        else None
                    ),
                    status=ExpenseStatus.RECORDED,
                    paid_by_user_id=manager.id,
                    recorded_by_user_id=manager.id,
                    idempotency_key=new_uuid(),
                )
            )


# --- entry point --------------------------------------------------------


def seed(db: Session) -> dict[str, int]:
    """Populate an empty database. Returns row counts per table."""
    if db.query(Location).count():
        raise RuntimeError("database already contains data; refusing to double-seed")

    used_names: set[str] = set()
    used_phones: set[str] = set()
    used_plates: set[str] = set()

    owner = User(
        email="owner@gvcexecutive.in",
        full_name="Ganesh Chinchakar",
        phone="9820011111",
        role=UserRole.SUPER_ADMIN,
        password_hash=hash_password("owner@123"),
        is_active=True,
    )
    db.add(owner)

    # Two owners today, more later. Both reach every building by role, so
    # neither needs a row in user_locations.
    co_owner = User(
        email="admin@gvcexecutive.in",
        full_name="Vaibhav Chinchakar",
        phone="9820022222",
        role=UserRole.SUPER_ADMIN,
        password_hash=hash_password("admin@123"),
        is_active=True,
    )
    db.add(co_owner)
    db.flush()

    specs = [
        # Kothrud mirrors the real building: 2 flats on the ground floor,
        # 3 on each of the next two, 2 on the top, and 402 is the only 3BHK.
        dict(
            name="Kothrud PG", code="KTD", city="Pune",
            layout=[2, 3, 3, 2], three_bhk=("402",), base_rent=8000,
        ),
        # The others are deliberately shaped differently, so the seat map is
        # proven to read a layout rather than assume one.
        dict(
            name="Baner PG", code="BNR", city="Pune",
            layout=[2, 2, 3], three_bhk=("101", "302"), base_rent=9000,
        ),
        dict(
            name="Hinjewadi PG", code="HJW", city="Pune",
            layout=[3, 3], three_bhk=("203",), base_rent=7500,
        ),
    ]

    # How the residents of each building are distributed across real-world
    # states. Weighted so most people are simply paid up.
    scenarios = (
        ["paid"] * 11 + ["defaulter"] * 3 + ["long_defaulter"] * 1
        + ["notice"] * 2 + ["left"] * 1
    )

    locations: list[Location] = []
    for index, spec in enumerate(specs):
        location, beds, bed_gender = _build_location(db, **spec)
        locations.append(location)

        manager = User(
            email=f"manager.{location.code.lower()}@gvcexecutive.in",
            full_name=_name(used_names),
            phone=_phone(used_phones),
            role=UserRole.MANAGER,
            password_hash=hash_password(f"{location.code.lower()}@123"),
            is_active=True,
        )
        db.add(manager)
        db.flush()
        db.add(UserLocation(user_id=manager.id, location_id=location.id))

        # Block one bed per building for repairs -- a real operational state
        # that must not count as rentable vacancy.
        beds[-1].status = BedStatus.BLOCKED
        beds[-1].notes = "Bathroom repair in progress"
        rentable = beds[:-1]

        # Fill about 80% of the building, leaving genuine vacancies.
        occupancy = 0.82 if index == 0 else (0.75 if index == 1 else 0.7)
        to_fill = int(len(rentable) * occupancy)
        chosen = RNG.sample(rentable, to_fill)

        for position, bed in enumerate(chosen):
            resident = _place_resident(
                db,
                location=location,
                bed=bed,
                marked_by=manager,
                used_names=used_names,
                used_phones=used_phones,
                scenario=scenarios[position % len(scenarios)],
                gender=(
                    Gender.FEMALE
                    if bed_gender[bed.id] == GenderPolicy.FEMALE
                    else Gender.MALE
                ),
            )
            _add_vehicles(
                db, location=location, resident=resident, used_plates=used_plates
            )

        # Expenses need the rent roll to scale against, so this runs after the
        # residents are in place.
        rent_roll = sum(
            b.default_rent for b in beds if b.status == BedStatus.OCCUPIED
        )
        _seed_expenses(
            db,
            location=location,
            owner=owner if index % 2 == 0 else co_owner,
            manager=manager,
            monthly_rent_roll=rent_roll,
        )

        # Hold a couple of the remaining empty beds for people arriving soon,
        # so the board has a real BOOKED state to show.
        still_empty = [b for b in rentable if b.status == BedStatus.AVAILABLE]
        for bed in RNG.sample(still_empty, min(2, len(still_empty))):
            _reserve_bed(
                db,
                location=location,
                bed=bed,
                user=manager,
                used_names=used_names,
                used_phones=used_phones,
                gender=(
                    Gender.FEMALE
                    if bed_gender[bed.id] == GenderPolicy.FEMALE
                    else Gender.MALE
                ),
            )

    db.add(
        AuditLog(
            user_id=owner.id,
            location_id=None,
            action=AuditAction.CREATE,
            entity_type="system",
            summary="Seeded development dataset",
        )
    )

    db.commit()

    from sqlalchemy import func, select

    counts: dict[str, int] = {}
    for model in (
        User, UserLocation, Location, Floor, Flat, Room, Bed, Resident,
        ResidentStay, RentRecord, Payment, Deposit, DepositRefund,
        MoveOutNotice, BedReservation, Vehicle,
        ExpenseTemplate, Expense, AuditLog,
    ):
        counts[model.__tablename__] = db.scalar(select(func.count()).select_from(model))
    return counts
