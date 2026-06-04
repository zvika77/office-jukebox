import os

from dotenv import load_dotenv

load_dotenv()  # loads TEST_DATABASE_URL from .env

import psycopg
import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jukebox_test"
)
# Point the app at the test database before importing app code
os.environ["DATABASE_URL"] = TEST_DSN

from app.auth import Identity, optional_identity, require_identity  # noqa: E402
from app.db import apply_schema  # noqa: E402
from app.main import app, seed_quick_adds  # noqa: E402


# Endpoint tests inject identity through X-Voter-Id / X-Display-Name headers
# instead of minting real Google JWTs. These overrides preserve that behavior;
# the real JWT verification path is covered directly in tests/test_auth.py.
def _fake_required(
    x_voter_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
) -> Identity:
    if not x_voter_id:
        raise HTTPException(status_code=401, detail="sign in required")
    return Identity(voter_id=x_voter_id, display_name=(x_display_name or x_voter_id))


def _fake_optional(
    x_voter_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
) -> Identity | None:
    if not x_voter_id:
        return None
    return Identity(voter_id=x_voter_id, display_name=(x_display_name or x_voter_id))


app.dependency_overrides[require_identity] = _fake_required
app.dependency_overrides[optional_identity] = _fake_optional

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
