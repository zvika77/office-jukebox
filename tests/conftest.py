import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import init_schema, set_connection_for_tests
from app.main import app, seed_quick_adds


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    set_connection_for_tests(conn)
    seed_quick_adds()
    yield conn
    conn.close()


@pytest.fixture
def client(db) -> TestClient:
    return TestClient(app)
