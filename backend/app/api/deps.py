"""Request dependencies: who is calling, and what they may touch."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import InvalidToken, decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.access import AccessContext, AccessDenied

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def client_ip(request: Request) -> str:
    """Best-effort caller address for rate limiting.

    Render terminates TLS at its proxy, so the socket address is always the
    proxy. `X-Forwarded-For` holds the real chain and its FIRST entry is the
    original client; later entries are the proxies it passed through.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the bearer token to a live, active user row.

    The user is re-read from the database on every request rather than trusted
    from the token, so deactivating an account takes effect immediately instead
    of when the token expires.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHENTICATED

    try:
        claims = decode_access_token(authorization.split(" ", 1)[1].strip())
        user_id = uuid.UUID(claims["sub"])
    except (InvalidToken, KeyError, ValueError):
        raise _UNAUTHENTICATED from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


def access_context(
    user: Annotated[User, Depends(current_user)],
) -> AccessContext:
    """The tenant scope for this request, rebuilt from live grants."""
    try:
        return AccessContext.from_user(user)
    except AccessDenied:
        raise _UNAUTHENTICATED from None


def require_super_admin(
    ctx: Annotated[AccessContext, Depends(access_context)],
) -> AccessContext:
    """Gate owner-only routes.

    404 rather than 403: a manager should not learn that an admin surface
    exists at all.
    """
    if not ctx.is_super_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ctx


CurrentUser = Annotated[User, Depends(current_user)]
Ctx = Annotated[AccessContext, Depends(access_context)]
AdminCtx = Annotated[AccessContext, Depends(require_super_admin)]
Db = Annotated[Session, Depends(get_db)]
