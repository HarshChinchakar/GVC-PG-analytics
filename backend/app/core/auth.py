"""Token issuing and brute-force protection.

Authentication is stateless: a signed JWT carries the user id and role, and the
browser never holds it in JavaScript (see the Next.js route handlers, which keep
it in a first-party httpOnly cookie).

PyJWT is used rather than python-jose because HS256 needs no `cryptography`
wheel -- that package alone would cost tens of megabytes of the 500 MB Render
budget for an algorithm the standard library already supports.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings

ALGORITHM = settings.jwt_algorithm


class InvalidToken(Exception):
    """Raised for any token that is missing, malformed, expired or mis-signed."""


def create_access_token(*, user_id: uuid.UUID, role: str, email: str) -> tuple[str, datetime]:
    """Issue a signed access token. Returns (token, expiry).

    The payload deliberately carries only identity and role -- never the list of
    granted locations. Those are re-read from the database on every request, so
    revoking a manager's access to a building takes effect immediately instead of
    waiting for their token to expire.
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify a token and return its claims, or raise InvalidToken.

    Every failure mode collapses to one exception type so that callers cannot
    accidentally treat "expired" and "forged" differently.
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc


# --- brute-force protection ---------------------------------------------


@dataclass
class _Bucket:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginThrottle:
    """Sliding-window lockout, held in process memory.

    In-memory rather than Redis on purpose: the application runs as a single
    Render instance (ADR-018), and adding a cache service to rate-limit perhaps
    a dozen logins a day would double the infrastructure for no gain. If the
    backend is ever scaled to multiple instances this must move to shared
    storage -- until then, per-process state is the whole picture.

    Attempts are counted per (email, client IP) so one attacker cannot lock a
    legitimate user out by guessing their address from elsewhere.
    """

    def __init__(self, max_attempts: int, lockout_seconds: int) -> None:
        self._max = max_attempts
        self._lockout = lockout_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _key(self, identifier: str, ip: str) -> str:
        return f"{identifier.lower()}|{ip}"

    def retry_after(self, identifier: str, ip: str) -> int:
        """Seconds the caller must wait, or 0 if they may attempt a login."""
        now = time.time()
        with self._lock:
            bucket = self._buckets.get(self._key(identifier, ip))
            if bucket and bucket.locked_until > now:
                return int(bucket.locked_until - now) + 1
        return 0

    def record_failure(self, identifier: str, ip: str) -> None:
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(self._key(identifier, ip), _Bucket())
            # Only failures inside the window count towards the lockout.
            bucket.failures = [t for t in bucket.failures if now - t < self._lockout]
            bucket.failures.append(now)
            if len(bucket.failures) >= self._max:
                bucket.locked_until = now + self._lockout
                bucket.failures.clear()

    def record_success(self, identifier: str, ip: str) -> None:
        with self._lock:
            self._buckets.pop(self._key(identifier, ip), None)

    def prune(self) -> None:
        """Drop stale buckets so the dict cannot grow without bound."""
        now = time.time()
        with self._lock:
            for key in [
                k
                for k, b in self._buckets.items()
                if b.locked_until < now and not b.failures
            ]:
                self._buckets.pop(key, None)


throttle = LoginThrottle(
    max_attempts=settings.login_max_attempts,
    lockout_seconds=settings.login_lockout_minutes * 60,
)
