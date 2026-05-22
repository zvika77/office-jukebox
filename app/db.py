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
    decade TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_votes_song_id ON votes(song_id);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


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
