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
