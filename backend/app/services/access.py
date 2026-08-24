"""The tenant-isolation boundary.

Every read and write in the application passes through here. The rule is
simple and absolute:

    No query touches an operational table without a location predicate
    derived from the authenticated user.

Isolation is enforced in *three independent layers*, so a mistake in one does
not become a data leak:

  1. Schema     -- every operational row carries `location_id` (see models).
  2. Service    -- `scope()` below adds the predicate to every statement.
  3. Database   -- Supabase Row Level Security, once we move to Postgres.

Layer 3 does not exist on SQLite, which is exactly why layer 2 is written as a
hard failure rather than a filter that silently returns nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy import Select
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.models.user import User

T = TypeVar("T", bound=Select[Any])


class AccessDenied(Exception):
    """Raised when a user reaches for a location they were not granted.

    The API layer maps this to HTTP 404, not 403 -- telling a manager that
    "location X exists but is not yours" is itself a leak of the owner's
    business. As far as a manager is concerned, other buildings do not exist.
    """

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class AccessContext:
    """Everything the data layer is allowed to know about the caller.

    Built once per request from the verified session token. Frozen so no code
    downstream can widen its own permissions mid-request.
    """

    user_id: uuid.UUID
    role: UserRole
    location_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @classmethod
    def from_user(cls, user: User) -> "AccessContext":
        if not user.is_active:
            raise AccessDenied("Inactive user")
        return cls(
            user_id=user.id,
            role=UserRole(user.role),
            location_ids=frozenset(user.granted_location_ids),
        )

    def can_access(self, location_id: uuid.UUID) -> bool:
        """Super admin sees every building; a manager sees only granted ones."""
        if self.is_super_admin:
            return True
        return location_id in self.location_ids

    def require(self, location_id: uuid.UUID) -> uuid.UUID:
        """Assert access to one location, or fail loudly.

        Call this before any write, and before any read that names a location
        explicitly. Returns the id so it can be used inline.
        """
        if not self.can_access(location_id):
            raise AccessDenied()
        return location_id


def visible_location_ids(ctx: AccessContext, db: Session) -> list[uuid.UUID]:
    """Locations this caller may see, resolved against the database.

    Super admins are resolved live rather than from the token, so a location
    added after they logged in is visible without a re-login.
    """
    if not ctx.is_super_admin:
        return list(ctx.location_ids)

    from sqlalchemy import select

    from app.models.location import Location

    stmt = select(Location.id).where(Location.is_active.is_(True))
    return list(db.scalars(stmt).all())


def scope(stmt: T, model: Any, ctx: AccessContext) -> T:
    """Add the tenant predicate to a SELECT.

    `model` must expose a `location_id` column -- that is the contract every
    operational table signs. A super admin is not filtered; a manager is
    narrowed to their granted locations, and a manager with no grants gets a
    predicate that matches nothing rather than a predicate that matches
    everything.
    """
    if ctx.is_super_admin:
        return stmt

    location_column = getattr(model, "location_id", None)
    if location_column is None:
        raise TypeError(
            f"{model.__name__} has no location_id; it cannot be tenant-scoped. "
            "Either add the column or handle this table explicitly."
        )

    if not ctx.location_ids:
        # An unassigned manager sees nothing. Returning an always-false
        # predicate is safer than returning the unfiltered statement.
        # sqlalchemy.false() renders as 0 on SQLite and false on Postgres.
        return stmt.where(sa_false())

    return stmt.where(location_column.in_(ctx.location_ids))


def assert_owned(entity: Any, ctx: AccessContext) -> Any:
    """Last-line check on a row that was fetched by primary key.

    Fetching by id bypasses `scope()`, so anything loaded that way must be
    re-checked before it is returned or modified.
    """
    if entity is None:
        raise AccessDenied()
    location_id = getattr(entity, "location_id", None)
    if location_id is None:
        raise TypeError(f"{type(entity).__name__} carries no location_id")
    ctx.require(location_id)
    return entity


# --- role gates ---------------------------------------------------------

#: Capabilities the owner keeps to themselves. Managers run the building day to
#: day; they do not see portfolio economics or manage access.
SUPER_ADMIN_ONLY = frozenset(
    {
        "manage_locations",
        "manage_users",
        "view_cross_location_analytics",
        "view_deposit_totals",
        "waive_rent",
        "delete_resident",
        "edit_rent_amount",
        "view_audit_log",
    }
)


def require_capability(ctx: AccessContext, capability: str) -> None:
    """Gate an owner-only action."""
    if capability in SUPER_ADMIN_ONLY and not ctx.is_super_admin:
        raise AccessDenied()
