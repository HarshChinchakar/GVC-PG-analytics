"""Runtime configuration.

Everything environment-specific lives here so that switching from SQLite to
Supabase Postgres is a change of one environment variable, not a code change.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PG Logistics & Rent Tally Portal"
    environment: str = "development"
    debug: bool = True

    # SQLite for development; swap for a Supabase pooled connection string in
    # production, e.g.
    #   postgresql+psycopg://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres
    database_url: str = f"sqlite+pysqlite:///{BACKEND_ROOT / 'pg_portal.db'}"

    # Echo SQL to stdout. Handy locally, must stay off in production.
    database_echo: bool = False

    # --- authentication -------------------------------------------------
    # MUST be overridden in production. Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(64))"
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 8 hours: one working day. Long enough that a manager is not logged out
    # mid-shift, short enough that a stolen token expires the same day.
    jwt_expire_minutes: int = 8 * 60

    # Brute-force protection, enforced in-process (single Render instance).
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    # Business rules that the owner may want to change without a code deploy.
    # These are defaults; each location can override them in its own row.
    default_notice_period_days: int = 30
    default_deposit_deduction: int = 1000

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


    def assert_production_ready(self) -> None:
        """Refuse to start a misconfigured production instance.

        Without this the worst failure is silent: if DATABASE_URL is not set on
        Render the app falls back to SQLite on the container's ephemeral disk,
        starts cleanly, appears to work, and loses every record on the next
        deploy or restart. Likewise a forgotten JWT_SECRET would leave every
        session signed with a key that is published in this repository.

        Failing loudly at boot is the only safe behaviour.
        """
        if self.environment != "production":
            return

        problems: list[str] = []
        if self.is_sqlite:
            problems.append(
                "DATABASE_URL is unset or points at SQLite. Production must use "
                "the Supabase Postgres connection string."
            )
        if self.jwt_secret == "dev-only-insecure-secret-change-me":
            problems.append(
                "JWT_SECRET is still the development default. Generate one with "
                '`python -c "import secrets; print(secrets.token_urlsafe(64))"`.'
            )
        if self.debug:
            problems.append("DEBUG must be false in production.")
        if not self.allowed_origins or "localhost" in self.cors_origins:
            problems.append(
                "CORS_ORIGINS must name the deployed frontend origin, not localhost."
            )
        if problems:
            raise RuntimeError(
                "Refusing to start — production configuration is incomplete:\n  - "
                + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
