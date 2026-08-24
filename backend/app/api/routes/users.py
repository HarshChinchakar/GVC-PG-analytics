"""Staff account management. Owner only.

Two rules are enforced here and nowhere else:
  * only a super admin may create accounts;
  * a super admin may only create MANAGERS, never another super admin.

The second rule matters more than it looks. It means a stolen owner session
cannot mint a second permanent owner account as a backdoor; the owner role can
only be granted by someone with direct database access.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AdminCtx, Db
from app.api.routes.auth import EMAIL_PATTERN
from app.core.enums import AuditAction, UserRole
from app.core.security import hash_password
from app.models import AuditLog, Location, User, UserLocation

router = APIRouter(prefix="/users", tags=["users"])


class CreateManagerRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    # 12 characters, not 8. These accounts hold every resident's phone number
    # and the owner's revenue figures.
    password: str = Field(min_length=12, max_length=200)
    location_ids: list[str] = Field(min_length=1)


class UserRow(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: str | None
    locations: list[str]


def _to_row(user: User, names: dict[uuid.UUID, str]) -> UserRow:
    return UserRow(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        locations=[names.get(g.location_id, "?") for g in user.location_grants],
    )


@router.get("", response_model=list[UserRow])
def list_users(ctx: AdminCtx, db: Db) -> list[UserRow]:
    names = {loc.id: loc.name for loc in db.scalars(select(Location)).all()}
    users = db.scalars(select(User).order_by(User.role, User.full_name)).all()
    return [_to_row(u, names) for u in users]


@router.post("", response_model=UserRow, status_code=status.HTTP_201_CREATED)
def create_manager(payload: CreateManagerRequest, ctx: AdminCtx, db: Db) -> UserRow:
    """Create a manager and grant them one or more buildings.

    The role is hard-coded to MANAGER -- it is not a field on the request, so
    there is no parameter an attacker could tamper with to escalate.
    """
    email = payload.email.strip().lower()

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists"
        )

    try:
        location_ids = [uuid.UUID(x) for x in payload.location_ids]
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid location") from None

    found = db.scalars(select(Location).where(Location.id.in_(location_ids))).all()
    if len(found) != len(set(location_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown location")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        role=UserRole.MANAGER,  # never taken from the request
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    for location_id in set(location_ids):
        db.add(UserLocation(user_id=user.id, location_id=location_id))

    db.add(
        AuditLog(
            user_id=ctx.user_id,
            action=AuditAction.CREATE,
            entity_type="users",
            entity_id=user.id,
            summary=f"Created manager {email}",
        )
    )
    db.commit()
    db.refresh(user)

    names = {loc.id: loc.name for loc in found}
    return _to_row(user, names)


@router.post("/{user_id}/deactivate", response_model=UserRow)
def deactivate(user_id: str, ctx: AdminCtx, db: Db) -> UserRow:
    """Disable an account. Deactivation, not deletion -- the audit trail holds
    RESTRICT foreign keys to this row, and rightly so."""
    try:
        parsed = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    user = db.get(User, parsed)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if user.id == ctx.user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account"
        )
    if user.role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Owner accounts cannot be deactivated here"
        )

    user.is_active = False
    db.add(
        AuditLog(
            user_id=ctx.user_id,
            action=AuditAction.UPDATE,
            entity_type="users",
            entity_id=user.id,
            summary=f"Deactivated {user.email}",
        )
    )
    db.commit()

    names = {loc.id: loc.name for loc in db.scalars(select(Location)).all()}
    return _to_row(user, names)
