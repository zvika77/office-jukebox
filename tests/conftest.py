import os

from dotenv import load_dotenv

load_dotenv()  # loads TEST_DATABASE_URL from .env

import psycopg
import pytest
from fastapi.testclient import TestClient

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jukebox_test"
)
# Point the app at the test database before importing app code
os.environ["DATABASE_URL"] = TEST_DSN

from app.db import apply_schema  # noqa: E402
from app.main import app, seed_quick_adds  # noqa: E402

_TABLES = "songs, votes, quick_adds, settings"


def _connect_or_skip() -> psycopg.Connection:
    try:
        return psycopg.connect(TEST_DSN, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("No test Postgres reachable at TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def _schema():
    conn = _connect_or_skip()
    apply_schema(conn)
    conn.close()
    yield


@pytest.fixture
def db(_schema):
    conn = _connect_or_skip()
    conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    conn.close()
    seed_quick_adds()
    yield


@pytest.fixture
def client(db) -> TestClient:
    return TestClient(app)
