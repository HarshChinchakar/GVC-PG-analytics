"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, dashboard, expenses, users
from app.core.config import settings
from app.services.access import AccessDenied

logging.basicConfig(level=logging.INFO if not settings.debug else logging.DEBUG)

# Fails the deploy rather than quietly running on an ephemeral SQLite file or a
# published signing key. Checked at import time so Render's health check never
# goes green on a broken configuration.
settings.assert_production_ready()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    # The interactive docs expose the full API shape. Useful locally; not
    # something to publish for a private business tool.
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline hardening headers.

    The API only ever returns JSON, so `nosniff` and a deny-all frame policy
    remove whole classes of browser-side mischief at no cost.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AccessDenied)
async def access_denied_handler(request: Request, exc: AccessDenied):
    """Cross-tenant access surfaces as 404, never 403.

    A 403 would confirm the resource exists, which leaks the owner's portfolio
    to a manager who guessed a URL.
    """
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not found"})


API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(expenses.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe. Render pings this to keep the free instance warm."""
    return {"status": "ok", "environment": settings.environment}
