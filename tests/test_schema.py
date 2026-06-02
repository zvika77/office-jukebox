import os

import psycopg
import pytest

from dotenv import load_dotenv

load_dotenv()

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jukebox_test"
)
os.environ.setdefault("DATABASE_URL", TEST_DSN)

from app.db import apply_schema  # noqa: E402


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(TEST_DSN, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("No test Postgres reachable at TEST_DATABASE_URL")
    c.execute("DROP TABLE IF EXISTS votes, songs, quick_adds, settings CASCADE")
    apply_schema(c)
    yield c
    c.close()


def test_apply_schema_creates_all_tables(conn):
    rows = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"songs", "votes", "quick_adds", "settings"} <= names


def test_songs_unique_on_youtube_id(conn):
    conn.execute(
        "INSERT INTO songs (id, youtube_id, title, thumbnail_url, added_by_name, added_at) "
        "VALUES ('a', 'abc12345678', 't', 'u', 'me', now())"
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO songs (id, youtube_id, title, thumbnail_url, added_by_name, added_at) "
            "VALUES ('b', 'abc12345678', 't', 'u', 'me', now())"
        )


def test_votes_unique_on_song_voter(conn):
    conn.execute(
        "INSERT INTO songs (id, youtube_id, title, thumbnail_url, added_by_name, added_at) "
        "VALUES ('s1', 'abc12345678', 't', 'u', 'me', now())"
    )
    conn.execute(
        "INSERT INTO votes (song_id, voter_id, created_at) VALUES ('s1', 'v1', now())"
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO votes (song_id, voter_id, created_at) VALUES ('s1', 'v1', now())"
        )
