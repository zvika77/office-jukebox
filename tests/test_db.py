import sqlite3

from app.db import init_schema


def test_init_schema_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"songs", "votes", "quick_adds"} <= tables


def test_songs_unique_on_youtube_id():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO songs (id, youtube_id, title, thumbnail_url, added_by_name, added_at) "
        "VALUES ('a', 'abc12345678', 't', 'u', 'me', '2026-01-01')"
    )
    try:
        conn.execute(
            "INSERT INTO songs (id, youtube_id, title, thumbnail_url, added_by_name, added_at) "
            "VALUES ('b', 'abc12345678', 't', 'u', 'me', '2026-01-01')"
        )
        raise AssertionError("Expected IntegrityError")
    except sqlite3.IntegrityError:
        pass


def test_votes_unique_on_song_voter():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO songs (id, youtube_id, title, thumbnail_url, added_by_name, added_at) "
        "VALUES ('s1', 'abc12345678', 't', 'u', 'me', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO votes (song_id, voter_id, created_at) VALUES ('s1', 'v1', '2026-01-01')"
    )
    try:
        conn.execute(
            "INSERT INTO votes (song_id, voter_id, created_at) VALUES ('s1', 'v1', '2026-01-01')"
        )
        raise AssertionError("Expected IntegrityError")
    except sqlite3.IntegrityError:
        pass
