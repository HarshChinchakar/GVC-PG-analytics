"""Local password hashing.

This IS the production credential path: the application authenticates against
its own `users` table rather than Supabase Auth, because the whole system has a
handful of staff accounts and adding a second identity provider would buy
nothing.

PBKDF2-HMAC-SHA256 from the standard library is used rather than bcrypt or
argon2id. Argon2id is the stronger choice in the abstract, but both pull
compiled wheels into an image that must fit Render's 500 MB limit. PBKDF2-SHA256
at 600,000 iterations is the OWASP-recommended parameter for this algorithm, so
the trade is a slower KDF for zero binary dependencies -- acceptable for a login
endpoint used a few times a day.

The format is self-describing (`algorithm$iterations$salt$hash`), so the
iteration count can be raised later without invalidating existing hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000  # OWASP guidance for PBKDF2-HMAC-SHA256
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    """Return `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`."""
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


#: A real hash of a random string. Verifying against this when the account does
#: not exist makes a miss cost the same as a hit, so response timing cannot be
#: used to discover which email addresses are registered.
_DUMMY_HASH = (
    "pbkdf2_sha256$600000$"
    "0f7c1e2d3a4b5c6d7e8f90a1b2c3d4e5$"
    "1f2ac0d8f6b4e2a09c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b"
)


def verify_dummy(password: str) -> bool:
    """Burn the same CPU as a real verification, for unknown accounts."""
    return verify_password(password or "x", _DUMMY_HASH)


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-time verification. False for any malformed or missing hash."""
    if not encoded or not password:
        return False
    try:
        algorithm, iterations_s, salt_hex, digest_hex = encoded.split("$")
        if algorithm != _ALGORITHM:
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations_s)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, actual)
