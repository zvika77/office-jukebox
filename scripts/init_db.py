"""One-shot: apply schema.sql and seed quick-adds to the database in DATABASE_URL.

Usage:
    DATABASE_URL=<supabase-pooler-or-direct-url> python scripts/init_db.py

Run once after creating the Supabase database (or any time you want to (re)seed
the curated quick-add list into an empty quick_adds table). Idempotent: schema
uses CREATE TABLE IF NOT EXISTS, and seeding is skipped when quick_adds is
non-empty.
"""

import psycopg

from app.db import _dsn, apply_schema
from app.main import seed_quick_adds


def main() -> None:
    with psycopg.connect(_dsn()) as conn:
        apply_schema(conn)
        conn.commit()
    seed_quick_adds()
    print("Schema applied and quick-adds seeded.")


if __name__ == "__main__":
    main()
