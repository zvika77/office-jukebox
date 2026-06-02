"""Postgres data access for Supabase.

Each operation opens a short-lived connection to the Supabase transaction-mode
pooler (DATABASE_URL, port 6543) and closes it when done. This suits serverless
invocations: there is no long-lived process to own a connection, and the pooler
keeps server-side connections warm. Client-side prepared statements are disabled
(prepare_threshold=None) because they do not survive transaction-mode pooling.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Read-friendly connection (autocommit). Closes on exit."""
    conn = psycopg.connect(
        _dsn(), autocommit=True, row_factory=dict_row, prepare_threshold=None
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """Write connection. Commits on success, rolls back on error, then closes."""
    conn = psycopg.connect(_dsn(), row_factory=dict_row, prepare_threshold=None)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_schema(conn: psycopg.Connection) -> None:
    """Run schema.sql against an open connection. Caller commits if needed."""
    sql = SCHEMA_PATH.read_text()
    for statement in (s for s in sql.split(";") if s.strip()):
        conn.execute(statement)
