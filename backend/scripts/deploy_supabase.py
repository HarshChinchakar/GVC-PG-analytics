"""Create the schema on Supabase Postgres and load data.

    SUPABASE_DB_URL='postgresql+psycopg://...' python -m scripts.deploy_supabase [--demo]

Reads the target from SUPABASE_DB_URL rather than DATABASE_URL, so running it
by accident cannot touch whatever the application is currently pointed at.

Without `--demo` it creates the schema and one owner account: a clean
production start.

With `--demo` it also loads the development dataset — three buildings, ~127
residents, three months of rent history — so a fresh deployment has something
to show. Every seeded account is then given a freshly generated password,
because the seed's development passwords (`owner@123` and friends) must never
be reachable from the public internet.

Credentials are printed once, at the end. They are not written to disk.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.enums import UserRole  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Base, User  # noqa: E402

#: Unambiguous alphabet -- no O/0, l/1/I. These get typed off a screen.
ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "O0lI1"
)


def strong_password(length: int = 18) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def build_engine(url: str):
    # Port 6543 is PgBouncer in transaction mode, which cannot hold server-side
    # prepared statements. See ADR-028.
    connect_args = {"prepare_threshold": None} if ":6543" in url else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy the schema to Supabase")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="also load the demo dataset (fictional residents)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="proceed even if our tables already exist",
    )
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        print("Set SUPABASE_DB_URL first, e.g.", file=sys.stderr)
        print(
            "  postgresql+psycopg://postgres.<ref>:<url-encoded-pw>"
            "@aws-0-<region>.pooler.supabase.com:6543/postgres",
            file=sys.stderr,
        )
        return 1
    if not url.startswith("postgresql"):
        print("SUPABASE_DB_URL must be a postgresql:// URL.", file=sys.stderr)
        return 1

    engine = build_engine(url)
    with engine.connect() as conn:
        version = conn.exec_driver_sql("select version()").scalar()
    print(f"Connected to {str(version).split(' on ')[0]}")

    existing = set(inspect(engine).get_table_names())
    ours = set(Base.metadata.tables)
    overlap = existing & ours
    if overlap and not args.force:
        print(
            f"\n{len(overlap)} of this application's tables already exist "
            f"({', '.join(sorted(overlap)[:4])}…).",
            file=sys.stderr,
        )
        print("Re-run with --force to create only what is missing.", file=sys.stderr)
        return 1

    Base.metadata.create_all(engine)
    print(f"Schema ready — {len(ours)} tables.")

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    credentials: list[tuple[str, str, str]] = []

    with Session() as db:
        if db.scalar(select(User)):
            print("\nAccounts already exist; leaving them untouched.")
        elif args.demo:
            from app.db.seed import seed

            counts = seed(db)
            print(f"\nDemo data loaded — {sum(counts.values())} rows:")
            width = max(len(n) for n in counts)
            for name, count in counts.items():
                print(f"  {name.ljust(width)}  {count:>5}")

            # The seed's passwords are published in this repository. Replace
            # every one of them before this database is reachable from the web.
            print("\nReplacing all seeded development passwords…")
            for user in db.scalars(select(User).order_by(User.role, User.email)).all():
                pw = strong_password()
                user.password_hash = hash_password(pw)
                credentials.append((user.role, user.email, pw))
            db.commit()
        else:
            print("\nCreate the owner account.")
            email = input("  Email: ").strip().lower()
            name = input("  Full name: ").strip()
            pw = strong_password()
            db.add(
                User(
                    email=email,
                    full_name=name,
                    role=UserRole.SUPER_ADMIN,
                    password_hash=hash_password(pw),
                    is_active=True,
                )
            )
            db.commit()
            credentials.append((UserRole.SUPER_ADMIN, email, pw))

    if credentials:
        print("\n" + "=" * 64)
        print("CREDENTIALS — shown once, not saved anywhere. Store them now.")
        print("=" * 64)
        for role, email, pw in credentials:
            label = "OWNER  " if role == UserRole.SUPER_ADMIN else "manager"
            print(f"  {label}  {email:<38} {pw}")
        print("=" * 64)

    print(
        "\nJWT_SECRET for Render (generate a fresh one per environment):\n  "
        + secrets.token_urlsafe(64)
    )
    print(
        "\nStill to do: add Row Level Security policies on location_id "
        "(see backend_architecure.md §9)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
