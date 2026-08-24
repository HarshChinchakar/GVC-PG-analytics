"""All ORM models.

Importing this package registers every mapper on `Base.metadata`, which is what
`create_all` and Alembic autogenerate need.
"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.deposit import Deposit, DepositRefund
from app.models.location import Bed, Flat, Floor, Location, Room
from app.models.moveout import MoveOutNotice
from app.models.occupancy import BedReservation, Vehicle, normalise_plate
from app.models.rent import Payment, RentRecord
from app.models.resident import Resident, ResidentStay
from app.models.user import User, UserLocation

__all__ = [
    "Base",
    "AuditLog",
    "Bed",
    "Deposit",
    "DepositRefund",
    "Flat",
    "Floor",
    "Location",
    "BedReservation",
    "MoveOutNotice",
    "Vehicle",
    "normalise_plate",
    "Payment",
    "RentRecord",
    "Resident",
    "ResidentStay",
    "Room",
    "User",
    "UserLocation",
]
