import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id TEXT PRIMARY KEY,
    youtube_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL,
    duration_seconds INTEGER,
    added_by_name TEXT NOT NULL,
    added_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    song_id TEXT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    voter_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (song_id, voter_id)
);

CREATE TABLE IF NOT EXISTS quick_adds (
    youtube_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL,
    decade TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_votes_song_id ON votes(song_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply pending migrations against an already-opened connection."""
    # Migration: make quick_adds.decade nullable (old schema had NOT NULL).
    cols = {row[1]: row for row in conn.execute("PRAGMA table_info(quick_adds)").fetchall()}
    if "decade" in cols and cols["decade"][3]:  # notnull flag == 1
        conn.executescript("""
            CREATE TABLE quick_adds_new (
                youtube_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                thumbnail_url TEXT NOT NULL,
                decade TEXT
            );
            INSERT INTO quick_adds_new SELECT youtube_id, title, thumbnail_url, decade FROM quick_adds;
            DROP TABLE quick_adds;
            ALTER TABLE quick_adds_new RENAME TO quick_adds;
        """)
        conn.commit()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_singleton: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Process-wide SQLite connection. Lazily initialized + schema-ensured."""
    global _singleton
    if _singleton is None:
        path = os.environ.get("DB_PATH", "jukebox.db")
        # Ensure the parent directory exists (needed when DB_PATH is on a mounted volume).
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        _singleton = _connect(path)
        init_schema(_singleton)
    return _singleton


def set_connection_for_tests(conn: sqlite3.Connection) -> None:
    """Replace the process-wide connection (used by test fixtures)."""
    global _singleton
    _singleton = conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
