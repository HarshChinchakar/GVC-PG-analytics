"""Authentication routes.

There is no registration endpoint by design: the owner creates manager accounts
from inside the application (see routes/users.py). A public sign-up form on a
private business tool is an attack surface with no user.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Ctx, CurrentUser, Db, client_ip
from app.core.auth import create_access_token, throttle
from app.core.security import verify_dummy, verify_password
from app.core.types import utcnow
from app.models import AuditLog, Location, User
from app.core.enums import AuditAction

router = APIRouter(prefix="/auth", tags=["auth"])

#: One message for every failure mode. Saying "no such user" versus "wrong
#: password" would let anyone enumerate valid staff email addresses.
_BAD_CREDENTIALS = "Incorrect email or password"


#: Deliberately not pydantic's EmailStr: that requires the `email-validator`
#: package, which drags in `dnspython` -- two dependencies and several MB of the
#: Render budget to validate a field we only ever compare against our own user
#: table. A shape check is all this needs.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=200)


class LocationOption(BaseModel):
    id: str
    name: str
    code: str
    city: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    expires_at: str
    user: "AuthUser"


class AuthUser(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    locations: list[LocationOption]


LoginResponse.model_rebuild()


def _accessible_locations(db, user: User) -> list[LocationOption]:
    """Buildings this user may open. Owner sees all active ones."""
    stmt = select(Location).where(Location.is_active.is_(True))
    if user.role != "super_admin":
        granted = user.granted_location_ids
        if not granted:
            return []
        stmt = stmt.where(Location.id.in_(granted))
    return [
        LocationOption(id=str(loc.id), name=loc.name, code=loc.code, city=loc.city)
        for loc in db.scalars(stmt.order_by(Location.name)).all()
    ]


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Db) -> LoginResponse:
    """Exchange credentials for a bearer token.

    Defences, in order:
      * lockout after repeated failures from the same (email, IP) pair;
      * one identical error for unknown email, wrong password and disabled
        account;
      * a dummy hash verification when the account does not exist, so a miss
        costs the same CPU time as a hit and timing reveals nothing.
    """
    ip = client_ip(request)
    email = payload.email.strip().lower()

    wait = throttle.retry_after(email, ip)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        verify_dummy(payload.password)
        throttle.record_failure(email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        throttle.record_failure(email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    throttle.record_success(email, ip)
    throttle.prune()

    token, expires = create_access_token(
        user_id=user.id, role=user.role, email=user.email
    )
    user.last_login_at = utcnow()
    db.add(
        AuditLog(
            user_id=user.id,
            action=AuditAction.LOGIN,
            entity_type="users",
            entity_id=user.id,
            summary=f"{user.email} signed in",
        )
    )
    db.commit()

    return LoginResponse(
        access_token=token,
        expires_at=expires.isoformat(),
        user=AuthUser(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            locations=_accessible_locations(db, user),
        ),
    )


@router.get("/me", response_model=AuthUser)
def me(user: CurrentUser, db: Db) -> AuthUser:
    """Who am I, and which buildings may I open."""
    return AuthUser(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        locations=_accessible_locations(db, user),
    )
