"""Create the schema and load development data.

    python -m scripts.init_db --reset

`--reset` drops everything first. Refuses to run against a non-SQLite database
so it can never be pointed at production Supabase by accident.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.seed import seed  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialise the development database")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    parser.add_argument("--no-seed", action="store_true", help="schema only")
    args = parser.parse_args()

    if args.reset and not settings.is_sqlite:
        print("Refusing to --reset a non-SQLite database.", file=sys.stderr)
        return 1

    print(f"Database: {settings.database_url}")

    if args.reset:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")

    Base.metadata.create_all(engine)
    print(f"Created {len(Base.metadata.tables)} tables.")

    if args.no_seed:
        return 0

    with SessionLocal() as db:
        counts = seed(db)

    width = max(len(name) for name in counts)
    print("\nSeeded rows:")
    for name, count in counts.items():
        print(f"  {name.ljust(width)}  {count:>5}")
    print(f"  {'TOTAL'.ljust(width)}  {sum(counts.values()):>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
