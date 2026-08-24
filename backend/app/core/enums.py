"""Domain enumerations.

Every enum here is persisted as a plain VARCHAR guarded by a CHECK constraint
rather than a native database ENUM type. Native PostgreSQL enums require an
ALTER TYPE dance on every value change and have no SQLite equivalent, which
would break the "SQLite now, Supabase Postgres later" goal.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Application user roles. Residents are NOT users -- they are records."""

    SUPER_ADMIN = "super_admin"
    MANAGER = "manager"


class Gender(StrEnum):
    """Resident gender.

    Needed because a PG is a shared-living business: flats are allocated by
    gender, and the owner needs to know which side of the building earns what.
    """

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class GenderPolicy(StrEnum):
    """Who a flat is allocated to.

    Held on the flat rather than the building because most PGs run male and
    female flats in the same block, often on different floors.
    """

    MALE = "male"
    FEMALE = "female"
    MIXED = "mixed"


class FlatType(StrEnum):
    """Physical configuration of a flat inside a building."""

    RK = "rk"  # single room with attached washroom
    BHK_1 = "1bhk"
    BHK_2 = "2bhk"
    BHK_3 = "3bhk"
    OTHER = "other"


class RoomKind(StrEnum):
    """What a room inside a flat is used as."""

    HALL = "hall"
    BEDROOM = "bedroom"


class BedStatus(StrEnum):
    """Lifecycle of a single sleeping position.

    Project.md lists "Available / Vacant / Occupied" in one place and
    "Occupied / To-be Vacant / Available" in another. We treat AVAILABLE and
    "vacant" as the same thing (an empty, rentable bed) and keep NOTICE for the
    "will free up on a known date" case, which is the genuinely distinct state.
    """

    AVAILABLE = "available"  # empty and rentable == "vacant"
    OCCUPIED = "occupied"  # someone is living here
    NOTICE = "notice"  # occupied, but resident has given notice
    BOOKED = "booked"  # reserved for someone arriving on a known date
    BLOCKED = "blocked"  # deliberately not rentable (repair, storage)


class ResidentStatus(StrEnum):
    """Lifecycle of a resident."""

    ACTIVE = "active"
    NOTICE = "notice"  # one-month notice served, still living here
    LEFT = "left"


class RentStatus(StrEnum):
    """A month's rent is binary -- the business takes no partial payments."""

    PENDING = "pending"
    PAID = "paid"
    WAIVED = "waived"  # owner-only escape hatch for corrections


class PaymentMethod(StrEnum):
    """How the money arrived. Recorded for the tally only; nothing is collected
    through this application."""

    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CHEQUE = "cheque"
    OTHER = "other"


class DepositStatus(StrEnum):
    """Where a security deposit currently stands."""

    HELD = "held"
    REFUNDED = "refunded"
    FORFEITED = "forfeited"


class NoticeStatus(StrEnum):
    """Lifecycle of a move-out notice."""

    ACTIVE = "active"  # notice served, move-out pending
    COMPLETED = "completed"  # resident actually left
    CANCELLED = "cancelled"  # resident withdrew the notice


class ReservationStatus(StrEnum):
    """Lifecycle of an advance booking."""

    HELD = "held"  # bed is reserved, person has not arrived
    CONVERTED = "converted"  # they moved in; a stay now exists
    CANCELLED = "cancelled"  # they backed out
    EXPIRED = "expired"  # move-in date passed with no arrival


class VehicleType(StrEnum):
    """What is parked outside."""

    TWO_WHEELER = "two_wheeler"
    FOUR_WHEELER = "four_wheeler"
    BICYCLE = "bicycle"
    OTHER = "other"


class ExpenseStatus(StrEnum):
    """An expense is never deleted -- money that was spent stays on the record.

    A mistake is voided, which keeps the row, the reason and who voided it.
    """

    RECORDED = "recorded"
    VOID = "void"


class ExpenseCategory(StrEnum):
    """What the money went on.

    A fixed list rather than free text: the whole point of this feature is a
    financial breakdown, and free-text categories produce "Electricity",
    "electricty" and "Light bill" as three separate lines.
    """

    # -- owner-only: the fixed cost of running the business
    SITE_RENT = "site_rent"
    SALARIES = "salaries"
    TAXES_LICENCES = "taxes_licences"
    INSURANCE = "insurance"
    LOAN_EMI = "loan_emi"
    DEPOSIT_REFUND = "deposit_refund"

    # -- day-to-day, recorded by whoever spent the money
    ELECTRICITY = "electricity"
    WATER = "water"
    GAS = "gas"
    GROCERIES = "groceries"
    HOUSEKEEPING = "housekeeping"
    REPAIRS = "repairs"
    INTERNET = "internet"
    LAUNDRY = "laundry"
    SECURITY = "security"
    TRANSPORT = "transport"
    STAFF_WELFARE = "staff_welfare"
    MARKETING = "marketing"
    MISC = "misc"


#: Categories only an owner may file. A manager runs the building day to day;
#: the lease, the payroll and the tax bill are not theirs to book, and letting
#: them would make the fixed-cost base editable by whoever holds a site login.
OWNER_ONLY_CATEGORIES: frozenset[str] = frozenset({
    ExpenseCategory.SITE_RENT,
    ExpenseCategory.SALARIES,
    ExpenseCategory.TAXES_LICENCES,
    ExpenseCategory.INSURANCE,
    ExpenseCategory.LOAN_EMI,
    ExpenseCategory.DEPOSIT_REFUND,
})

#: Display names and grouping, served to the UI so the form cannot drift out of
#: step with what the database will accept.
CATEGORY_META: dict[str, dict[str, object]] = {
    ExpenseCategory.SITE_RENT:      {"label": "Site rent",        "group": "Fixed",     "recurring": True},
    ExpenseCategory.SALARIES:       {"label": "Salaries",         "group": "Fixed",     "recurring": True},
    ExpenseCategory.TAXES_LICENCES: {"label": "Taxes & licences", "group": "Fixed",     "recurring": False},
    ExpenseCategory.INSURANCE:      {"label": "Insurance",        "group": "Fixed",     "recurring": False},
    ExpenseCategory.LOAN_EMI:       {"label": "Loan / EMI",       "group": "Fixed",     "recurring": True},
    ExpenseCategory.DEPOSIT_REFUND: {"label": "Deposit refunded", "group": "Fixed",     "recurring": False},
    ExpenseCategory.ELECTRICITY:    {"label": "Electricity",      "group": "Utilities", "recurring": True},
    ExpenseCategory.WATER:          {"label": "Water",            "group": "Utilities", "recurring": True},
    ExpenseCategory.GAS:            {"label": "Gas / LPG",        "group": "Utilities", "recurring": True},
    ExpenseCategory.INTERNET:       {"label": "Internet",         "group": "Utilities", "recurring": True},
    ExpenseCategory.GROCERIES:      {"label": "Groceries",        "group": "Running",   "recurring": False},
    ExpenseCategory.HOUSEKEEPING:   {"label": "Housekeeping",     "group": "Running",   "recurring": False},
    ExpenseCategory.REPAIRS:        {"label": "Repairs",          "group": "Running",   "recurring": False},
    ExpenseCategory.LAUNDRY:        {"label": "Laundry",          "group": "Running",   "recurring": False},
    ExpenseCategory.SECURITY:       {"label": "Security",         "group": "Running",   "recurring": True},
    ExpenseCategory.TRANSPORT:      {"label": "Transport",        "group": "Running",   "recurring": False},
    ExpenseCategory.STAFF_WELFARE:  {"label": "Staff welfare",    "group": "Running",   "recurring": False},
    ExpenseCategory.MARKETING:      {"label": "Marketing",        "group": "Running",   "recurring": False},
    ExpenseCategory.MISC:           {"label": "Miscellaneous",    "group": "Running",   "recurring": False},
}


class PaidFrom(StrEnum):
    """Whose money left the building.

    Without this a manager buying cleaning supplies out of pocket is
    indistinguishable from petty cash, and nobody ever pays them back.
    """

    SITE_CASH = "site_cash"        # petty cash held at the PG
    BUSINESS_ACCOUNT = "business_account"
    PERSONAL = "personal"          # someone paid themselves; owed back


class AuditAction(StrEnum):
    """Coarse action verbs for the audit trail."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    MARK_PAID = "mark_paid"
    UNMARK_PAID = "unmark_paid"
    ASSIGN_BED = "assign_bed"
    RELEASE_BED = "release_bed"
    SERVE_NOTICE = "serve_notice"
    RESERVE_BED = "reserve_bed"
    REFUND_DEPOSIT = "refund_deposit"
    RECORD_EXPENSE = "record_expense"
    VOID_EXPENSE = "void_expense"


def values(enum_cls: type[StrEnum]) -> list[str]:
    """Return an enum's raw string values, for CHECK constraint generation."""
    return [member.value for member in enum_cls]


def sql_in(column: str, enum_cls: type[StrEnum]) -> str:
    """Build a portable `column IN ('a','b')` CHECK expression.

    This is what keeps the enum honest at the database level on both SQLite and
    Postgres, without using a native ENUM type.
    """
    allowed = ", ".join(f"'{v}'" for v in values(enum_cls))
    return f"{column} IN ({allowed})"
