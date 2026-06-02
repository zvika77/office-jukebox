# Vercel + Supabase Migration — Phase 1 (Platform Port) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the *exact same* Office Jukebox app on Vercel's Python serverless runtime with Supabase Postgres as the database and ~4s polling in place of SSE — anonymous name-prompt identity unchanged. Independently shippable; Google auth is Phase 2.

**Architecture:** FastAPI stays, but the data layer swaps SQLite for psycopg3 against the Supabase transaction-mode pooler, opening a short-lived connection per operation (no process-wide singleton, no client-side pool — the serverless model and the pooler make per-call connect/close the simplest correct choice). The SSE broker is deleted and both the phone and TV poll every 4 seconds. A thin `api/index.py` exposes the ASGI `app` to Vercel; `vercel.json` routes everything to that function (static included) for behavioral parity. Schema lives in a checked-in `schema.sql`, applied once out-of-band — no DDL on cold start.

**Tech Stack:** Python 3, FastAPI, psycopg3 (`psycopg[binary]`), Supabase Postgres, Vercel Python runtime, pytest + FastAPI `TestClient`, vanilla JS frontend.

---

## Deviations from the spec (read before starting)

1. **No client-side connection pool.** The spec's design section discussed psycopg + the pooler; this plan deliberately uses per-operation `psycopg.connect()`/`close()` rather than `psycopg_pool`. Rationale: serverless functions freeze between invocations (a pool's background maintenance thread misbehaves), and Supabase's transaction-mode pooler already pools server-side. Per-call connect to the pooler is fast and unambiguously correct. This is a documented tradeoff; a request-scoped single connection is a possible later optimization, out of scope here.
2. **Static served *through* the function, not the CDN.** The spec sketched serving `index.html`/`jukebox.html`/`styles.css` from Vercel's CDN with only `/api/*` hitting the function. For Phase 1 we route **everything** to the FastAPI function (it already serves static via `StaticFiles` + `FileResponse`). This guarantees parity and sidesteps Vercel rewrite-ordering bugs. CDN optimization is a safe follow-up, out of scope here.
3. **Tests require a real Postgres.** Per spec §1.4, the SQLite in-memory fixture is replaced with a Postgres test database (local Docker). When no test Postgres is reachable, DB-dependent tests **skip** (loudly) rather than fail, so pure unit tests (`test_youtube`, `test_identity`) still run on a bare checkout.

---

## Prerequisites (one-time, before Task 1)

- A local Postgres for the test suite. Quickest path:
  ```bash
  docker run -d --name jukebox-test-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=jukebox_test -p 5432:5432 postgres:16
  ```
  The fixtures default to `postgresql://postgres:postgres@localhost:5432/jukebox_test`. Override with `TEST_DATABASE_URL` if your setup differs.
- A Supabase project (you already have one). You'll need its **transaction-mode pooler** connection string (port `6543`) for deploy, and a direct/pooler string to apply the schema once.

---

## Task ordering & the "red window"

Task 1 ports the entire data layer in one cohesive task with bite-sized steps, ending with the **full pytest suite green**. This avoids leaving the suite broken between tasks (a pure SQL-dialect port can't be meaningfully half-converted and still pass). Tasks 2–6 each also end green (or with explicit manual verification for the JS/deploy tasks).

---

### Task 1: Port the data layer from SQLite to Supabase Postgres

This is the core task. It replaces the driver, the schema, the test fixtures, and converts every SQL statement to Postgres dialect. SSE is left untouched here (removed in Task 2).

**Files:**
- Modify: `requirements.txt`
- Create: `schema.sql`
- Rewrite: `app/db.py`
- Rewrite: `tests/conftest.py`
- Create: `tests/test_schema.py`
- Delete: `tests/test_db.py` (SQLite-specific; replaced by `test_schema.py`)
- Modify: `app/voting.py`
- Modify: `app/main.py` (SQL dialect + read-site connection handling only; SSE stays)

- [ ] **Step 1: Add psycopg to requirements**

Edit `requirements.txt` — add the psycopg line (leave `sse-starlette` for now; Task 2 removes it):

```
fastapi>=0.110
uvicorn[standard]>=0.27
httpx>=0.27
sse-starlette>=2.0
psycopg[binary]>=3.1
qrcode[pil]>=7.4
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-httpx>=0.30
```

Install: `pip install -r requirements.txt`

- [ ] **Step 2: Write `schema.sql`**

Create `schema.sql` at the repo root. Note `quick_adds.seq` — a `GENERATED ALWAYS AS IDENTITY` column that gives a stable insertion order to replace SQLite's `ORDER BY rowid`. `decade` stays nullable (playlist mode inserts NULL).

```sql
CREATE TABLE IF NOT EXISTS songs (
    id text PRIMARY KEY,
    youtube_id text NOT NULL UNIQUE,
    title text NOT NULL,
    thumbnail_url text NOT NULL,
    duration_seconds integer,
    added_by_name text NOT NULL,
    added_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    song_id text NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    voter_id text NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (song_id, voter_id)
);

CREATE TABLE IF NOT EXISTS quick_adds (
    seq bigint GENERATED ALWAYS AS IDENTITY,
    youtube_id text PRIMARY KEY,
    title text NOT NULL,
    thumbnail_url text NOT NULL,
    decade text
);

CREATE TABLE IF NOT EXISTS settings (
    key text PRIMARY KEY,
    value text
);

CREATE INDEX IF NOT EXISTS idx_votes_song_id ON votes(song_id);
```

- [ ] **Step 3: Rewrite `app/db.py`**

Replace the entire file. `get_connection()` (autocommit, for reads) and `transaction()` (commit/rollback, for writes) are both context managers now. `dict_row` makes rows behave like `sqlite3.Row` (`row["col"]`). `prepare_threshold=None` disables client-side prepared statements that don't survive transaction-mode pooling.

```python
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
```

Note what's gone: `init_schema`, `_migrate`, `_connect`, the `_singleton`, and `set_connection_for_tests`. Tests now manage a real database instead of injecting a connection.

- [ ] **Step 4: Rewrite `tests/conftest.py`**

Replace the entire file. It points the app's `DATABASE_URL` at the test database *before* importing the app, applies the schema once per session, and truncates + reseeds before each test. DB tests skip (not fail) when no Postgres is reachable.

```python
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jukebox_test"
)
# The app reads DATABASE_URL when it connects; point it at the test database.
os.environ["DATABASE_URL"] = TEST_DSN

from app.db import apply_schema  # noqa: E402  (must follow the env var assignment)
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
```

The `db` and `client` fixture *names* are unchanged, so existing test bodies that request them need no edits.

- [ ] **Step 5: Create `tests/test_schema.py` and delete `tests/test_db.py`**

Delete the SQLite-specific `tests/test_db.py`. Create `tests/test_schema.py` to cover schema creation + the two uniqueness constraints against Postgres:

```python
import os

import psycopg
import pytest

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
```

This `conn` fixture uses the default tuple row factory, so `r[0]` is correct.

- [ ] **Step 6: Convert `app/voting.py` to Postgres dialect**

Two edits: wrap the read in `get_connection()` and change `?`→`%s`. The `ON CONFLICT(key) DO UPDATE SET value = excluded.value` is already valid Postgres.

Replace `get_deadline`:

```python
def get_deadline() -> datetime | None:
    """Return the deadline as a timezone-aware UTC datetime, or None when unset."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = %s", (_KEY,)
        ).fetchone()
    if not row or not row["value"]:
        return None
    raw = row["value"].replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
```

Replace `set_deadline`:

```python
def set_deadline(dt: datetime | None) -> None:
    """Store the deadline (UTC), or clear it when given None."""
    with transaction() as conn:
        if dt is None:
            conn.execute("DELETE FROM settings WHERE key = %s", (_KEY,))
            return
        iso = dt.astimezone(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (_KEY, iso),
        )
```

`voting_is_open()` is pure Python over `get_deadline()` — no change.

- [ ] **Step 7: Convert `app/main.py` SQL + read-site connection handling**

SSE imports and `publish_sync(...)` calls stay (Task 2 removes them). Apply each edit below.

**7a — `seed_quick_adds`** (`fetchone()[0]` → `["n"]`, `?`→`%s`, wrap read):

```python
def seed_quick_adds() -> None:
    """Seed from hardcoded list only when the table is empty."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM quick_adds").fetchone()["n"]
    if count > 0:
        return
    with transaction() as tx:
        for entry in QUICK_ADDS:
            tx.execute(
                "INSERT INTO quick_adds (youtube_id, title, thumbnail_url, decade) "
                "VALUES (%s, %s, %s, %s)",
                (
                    entry["youtube_id"],
                    entry["title"],
                    thumbnail_for(entry["youtube_id"]),
                    entry["decade"],
                ),
            )
```

**7b — `list_quick_adds`** (wrap read):

```python
@app.get("/api/quick-adds")
def list_quick_adds() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT youtube_id, title, thumbnail_url, decade FROM quick_adds ORDER BY decade, title"
        ).fetchall()
    return [dict(row) for row in rows]
```

**7c — `_do_refresh`** — change `?`→`%s` in both `INSERT INTO quick_adds` statements (inside the two `with transaction() as conn:` blocks), and replace the final read block. The playlist-mode insert:

```python
                conn.execute(
                    "INSERT INTO quick_adds (youtube_id, title, thumbnail_url, decade) VALUES (%s, %s, %s, %s)",
                    (s["youtube_id"], s["title"], s["thumbnail_url"], None),
                )
```

The decade-fallback insert:

```python
                conn.execute(
                    "INSERT INTO quick_adds (youtube_id, title, thumbnail_url, decade) VALUES (%s, %s, %s, %s)",
                    (s["youtube_id"], s["title"], s["thumbnail_url"], s.get("decade")),
                )
```

The final read (replaces `ORDER BY rowid` with `ORDER BY seq`, wraps in `get_connection()`):

```python
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT youtube_id, title, thumbnail_url, decade FROM quick_adds ORDER BY seq"
        ).fetchall()
    return [dict(row) for row in rows]
```

**7d — `add_song`** — wrap the existence read, convert placeholders, and use `ON CONFLICT` for the idempotent vote insert. Replace the body from the existence check onward:

```python
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM songs WHERE youtube_id = %s", (video_id,)
        ).fetchone()

    if existing:
        song_id = existing["id"]
        with transaction() as tx:
            tx.execute(
                "INSERT INTO votes (song_id, voter_id, created_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (song_id, voter_id) DO NOTHING",
                (song_id, identity.voter_id, _now()),
            )
        publish_sync("songs_changed")
        return JSONResponse(
            status_code=200,
            content={"id": song_id, "already_in_list": True},
        )

    meta = fetch_video_metadata(video_id)
    song_id = str(uuid.uuid4())
    with transaction() as tx:
        tx.execute(
            "INSERT INTO songs (id, youtube_id, title, thumbnail_url, duration_seconds, added_by_name, added_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (song_id, video_id, meta.title, meta.thumbnail_url, None, identity.display_name, _now()),
        )

    publish_sync("songs_changed")
```

**7e — `list_songs`** — wrap read, `= ?`→`= %s`:

```python
@app.get("/api/songs")
def list_songs(identity: Identity = Depends(require_identity)) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id, s.youtube_id, s.title, s.thumbnail_url, s.added_by_name, s.added_at,
                COUNT(v.voter_id) AS votes,
                SUM(CASE WHEN v.voter_id = %s THEN 1 ELSE 0 END) AS did_i_vote_count
            FROM songs s
            LEFT JOIN votes v ON v.song_id = s.id
            GROUP BY s.id
            ORDER BY votes DESC, s.added_at ASC
            """,
            (identity.voter_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "youtube_id": row["youtube_id"],
            "title": row["title"],
            "thumbnail_url": row["thumbnail_url"],
            "added_by_name": row["added_by_name"],
            "added_at": row["added_at"],
            "votes": row["votes"],
            "did_i_vote": bool(row["did_i_vote_count"]),
        }
        for row in rows
    ]
```

`GROUP BY s.id` is valid because `s.id` is the primary key (Postgres allows selecting other `s.*` columns under functional dependency). `added_at` comes back as a `datetime`; FastAPI's encoder serializes it to ISO — the frontend ignores this field, so the wire format change is invisible.

**7f — `toggle_vote`** — three short connection scopes (existence read, write transaction, count read):

```python
@app.post("/api/songs/{song_id}/vote")
def toggle_vote(
    song_id: str,
    identity: Identity = Depends(require_identity),
) -> dict:
    if not voting_is_open():
        raise HTTPException(status_code=403, detail="Voting has closed")

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM songs WHERE id = %s", (song_id,)
        ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="song not found")

    with transaction() as tx:
        cur = tx.execute(
            "DELETE FROM votes WHERE song_id = %s AND voter_id = %s",
            (song_id, identity.voter_id),
        )
        if cur.rowcount == 0:
            tx.execute(
                "INSERT INTO votes (song_id, voter_id, created_at) VALUES (%s, %s, %s)",
                (song_id, identity.voter_id, _now()),
            )
            did_i_vote = True
        else:
            did_i_vote = False

    with get_connection() as conn:
        votes = conn.execute(
            "SELECT COUNT(*) AS c FROM votes WHERE song_id = %s", (song_id,)
        ).fetchone()["c"]
    publish_sync("songs_changed")
    return {"id": song_id, "did_i_vote": did_i_vote, "votes": votes}
```

**7g — `play`** — wrap read:

```python
@app.post("/api/play")
def play(_: None = Depends(require_admin)) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.youtube_id, s.title, s.thumbnail_url,
                   COUNT(v.voter_id) AS votes
            FROM songs s
            LEFT JOIN votes v ON v.song_id = s.id
            GROUP BY s.id
            ORDER BY votes DESC, s.added_at ASC
            LIMIT 3
            """
        ).fetchall()
    return {
        "queue": [
            {
                "id": row["id"],
                "youtube_id": row["youtube_id"],
                "title": row["title"],
                "thumbnail_url": row["thumbnail_url"],
                "votes": row["votes"],
            }
            for row in rows
        ]
    }
```

**7h — `reset_day`** — no placeholders to change (the only literal is `'voting_deadline'`); already uses `with transaction()`. Leave it exactly as-is, including the two `publish_sync(...)` calls.

- [ ] **Step 8: Run the full suite — expect green**

Run: `pytest -q`
Expected: PASS. `test_schema.py` exercises the Postgres schema; all the API tests (`test_songs_api`, `test_votes_api`, `test_quick_adds_api`, `test_admin_api`, `test_voting_api`, `test_voting`, `test_identity`, `test_youtube`, `test_health`, `test_admin`) pass against the test Postgres. `test_events.py` still passes (SSE removed in Task 2).

If `test_youtube`/`test_identity` are the only ones running and DB tests skip, your test Postgres isn't up — start the Docker container from Prerequisites and re-run.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt schema.sql app/db.py app/voting.py app/main.py tests/conftest.py tests/test_schema.py
git rm tests/test_db.py
git commit -m "feat: port data layer from SQLite to Supabase Postgres (psycopg3)"
```

---

### Task 2: Remove SSE from the backend (polling replaces it)

Serverless functions can't hold an open SSE stream, so the broker and `/api/events` go away. The frontend switches to polling in Task 3.

**Files:**
- Delete: `app/events.py`
- Delete: `tests/test_events.py`
- Modify: `app/main.py` (remove SSE import, route, and `publish_sync(...)` calls)
- Modify: `requirements.txt` (remove `sse-starlette`)

- [ ] **Step 1: Delete the broker and its test**

```bash
git rm app/events.py tests/test_events.py
```

- [ ] **Step 2: Remove SSE from `app/main.py`**

Remove these two import lines near the top:

```python
from sse_starlette.sse import EventSourceResponse
```
```python
from app.events import broker, publish_sync
```

Remove the entire `/api/events` route:

```python
@app.get("/api/events")
async def events():
    async def stream():
        async with broker.subscribe() as queue:
            yield {"event": "hello", "data": "connected"}
            while True:
                message = await queue.get()
                yield {"event": message, "data": message}

    return EventSourceResponse(stream())
```

Delete every `publish_sync(...)` call. There are five: two `publish_sync("songs_changed")` in `add_song`, one `publish_sync("songs_changed")` in `toggle_vote`, and `publish_sync("songs_changed")` + `publish_sync("deadline_changed")` in `reset_day`. Also remove the `publish_sync("deadline_changed")` in `set_voting_deadline`. After removal, those functions simply return their dict as before.

- [ ] **Step 3: Remove `sse-starlette` from `requirements.txt`**

Delete the line:

```
sse-starlette>=2.0
```

- [ ] **Step 4: Verify nothing still references SSE**

Run: `grep -rn "publish_sync\|sse_starlette\|EventSource\|app.events\|/api/events" app/ tests/`
Expected: no matches in Python (`app/static/*.js` still references `EventSource`/`/api/events` — that's removed in Task 3).

- [ ] **Step 5: Run the suite — expect green**

Run: `pytest -q`
Expected: PASS. `test_events.py` is gone; nothing else depended on the broker.

- [ ] **Step 6: Commit**

```bash
git add app/main.py requirements.txt
git commit -m "refactor: remove SSE broker and /api/events (polling replaces it)"
```

---

### Task 3: Switch the frontend from SSE to ~4s polling

No automated tests (vanilla JS); verification is manual in a browser.

**Files:**
- Modify: `app/static/phone.js`
- Modify: `app/static/jukebox.js`

- [ ] **Step 1: `phone.js` — remove `setupSSE`**

Delete the function:

```javascript
function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", loadSongs);
    source.addEventListener("deadline_changed", loadDeadline);
}
```

- [ ] **Step 2: `phone.js` — poll instead, in `startApp`**

In `startApp()`, remove the `setupSSE();` call, tighten the song poll to 4s, and add a deadline poll. Replace:

```javascript
    setupSSE();
    loadQuickAdds();
    loadSongs();
    loadDeadline();
    setInterval(loadSongs, 10000);
    setInterval(updateCountdown, 1000);
```

with:

```javascript
    loadQuickAdds();
    loadSongs();
    loadDeadline();
    setInterval(loadSongs, 4000);
    setInterval(loadDeadline, 4000);
    setInterval(updateCountdown, 1000);
```

(The local 1s `updateCountdown` tick stays — it's pure client-side, no network.)

- [ ] **Step 3: `jukebox.js` — remove `setupSSE`**

Delete the function:

```javascript
function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", refresh);
    source.addEventListener("deadline_changed", loadDeadline);
}
```

- [ ] **Step 4: `jukebox.js` — poll instead, at the bottom**

Replace the bottom startup block:

```javascript
document.getElementById("public-url").textContent = location.origin;
setupAdmin();
setupSSE();
refresh();
loadDeadline();
setInterval(updateCountdown, 1000);
```

with:

```javascript
document.getElementById("public-url").textContent = location.origin;
setupAdmin();
refresh();
loadDeadline();
setInterval(refresh, 4000);
setInterval(loadDeadline, 4000);
setInterval(updateCountdown, 1000);
```

- [ ] **Step 5: Manual verification (local)**

Run the app locally against the test (or a scratch Supabase) database:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/jukebox_test uvicorn app.main:app --reload
```

Open `http://localhost:8000/` (phone) and `http://localhost:8000/jukebox?admin=<ADMIN_TOKEN>` (TV) in two tabs. Confirm:
- No console errors mentioning `EventSource` or `/api/events`.
- Adding/voting a song on the phone reflects on the TV within ~4s (and vice-versa).
- The countdown banner updates every second; setting a deadline on the TV shows up on the phone within ~4s.

- [ ] **Step 6: Commit**

```bash
git add app/static/phone.js app/static/jukebox.js
git commit -m "refactor: replace SSE with 4s polling on phone and TV"
```

---

### Task 4: Remove the startup hook; add `scripts/init_db.py`

Vercel's serverless runtime has no reliable startup lifecycle and a read-only filesystem, so we stop doing DDL/seeding/playlist-refresh on boot. Schema + seed are applied out-of-band by a one-shot script (and the existing `POST /api/quick-adds/refresh` still pulls the playlist on demand).

**Files:**
- Modify: `app/main.py` (delete the `@app.on_event("startup")` handler)
- Create: `scripts/init_db.py`

- [ ] **Step 1: Delete the startup handler in `app/main.py`**

Remove the whole block:

```python
@app.on_event("startup")
def on_startup() -> None:
    get_connection()
    seed_quick_adds()
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if api_key:
        try:
            _do_refresh(api_key)
        except Exception as exc:
            # Log but don't crash — the container should still come up
            import sys
            print(f"[startup] quick-add refresh failed (will retry on next /refresh): {exc}", file=sys.stderr)
```

`seed_quick_adds`, `_do_refresh`, and `get_connection` all remain defined and used elsewhere — only the boot hook goes. (Tests never triggered startup: `conftest` builds `TestClient(app)` without the `with` context, so this removal can't affect them.)

- [ ] **Step 2: Create `scripts/init_db.py`**

```python
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
```

- [ ] **Step 3: Verify the script runs against the test DB**

Run:
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/jukebox_test python scripts/init_db.py
```
Expected: prints `Schema applied and quick-adds seeded.` with no traceback. Re-running prints the same (idempotent — seeding is skipped the second time).

- [ ] **Step 4: Run the suite — expect green**

Run: `pytest -q`
Expected: PASS (unchanged — no test depended on the startup hook).

- [ ] **Step 5: Commit**

```bash
git add app/main.py scripts/init_db.py
git commit -m "refactor: move schema+seed out of startup hook into scripts/init_db.py"
```

---

### Task 5: Vercel deployment files

Expose the ASGI app to Vercel and route all traffic to it. No automated tests — verification is a real deploy + smoke test.

**Files:**
- Create: `api/index.py`
- Create: `vercel.json`

- [ ] **Step 1: Create `api/index.py`**

Vercel's Python runtime serves an ASGI app exported as `app` from a file under `api/`.

```python
from app.main import app  # noqa: F401  (Vercel's Python runtime serves this ASGI app)
```

- [ ] **Step 2: Create `vercel.json`**

Routes everything to the function (see Deviation #2). `includeFiles: "app/**"` ensures the static HTML/JS/CSS are bundled so `FileResponse("app/static/...")` and `StaticFiles(directory="app/static")` work at runtime. `requirements.txt` at the repo root is auto-detected.

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python",
      "config": { "includeFiles": "app/**" }
    }
  ],
  "routes": [
    { "src": "/(.*)", "dest": "api/index.py" }
  ]
}
```

- [ ] **Step 3: Apply the schema to the real Supabase database**

Either run the init script locally against Supabase (use the pooler URL, port `6543`):
```bash
DATABASE_URL='postgresql://postgres.<ref>:<password>@<host>:6543/postgres' python scripts/init_db.py
```
…or paste the contents of `schema.sql` into the Supabase SQL editor and run it, then hit `POST /api/quick-adds/refresh` (or run the script) to seed.

- [ ] **Step 4: Set Vercel environment variables**

In the Vercel project settings (or via `vercel env add`), set:
- `DATABASE_URL` — Supabase **transaction-mode pooler** URL (port `6543`).
- `ADMIN_TOKEN` — same secret used today.
- `YOUTUBE_API_KEY` — for `/api/quick-adds/refresh`.
- `YOUTUBE_PLAYLIST_ID` — optional; the curated playlist source.
- `PUBLIC_URL` — the deployed Vercel URL (e.g. `https://office-jukebox.vercel.app`) so `/api/qrcode.png` encodes the right address.

- [ ] **Step 5: Deploy and smoke-test**

Deploy (push to the Vercel-connected branch, or `vercel --prod`). Then verify on the deployed domain:
- `GET /healthz` → `{"status":"ok"}`.
- `GET /` loads the phone view; `GET /jukebox?admin=<ADMIN_TOKEN>` loads the TV view with admin controls; `GET /jukebox` (no token) hides admin controls.
- `GET /api/quick-adds` returns the seeded list.
- Add a song from the phone; it appears on the TV within ~4s.
- `GET /api/qrcode.png` renders a QR encoding `PUBLIC_URL`.

If routing misbehaves (e.g. static assets 404, or `/api/*` not reaching the function), this is the spec's known Vercel-routing risk — adjust `routes`/`builds` in `vercel.json` and redeploy. Capture the working config before moving on.

- [ ] **Step 6: Commit**

```bash
git add api/index.py vercel.json
git commit -m "feat: add Vercel Python function entrypoint and routing"
```

---

### Task 6: Update docs and final cleanup

**Files:**
- Modify: `README.md`
- Optional: remove Railway leftovers (`Procfile`, `railway.toml`)

- [ ] **Step 1: Update `README.md`**

Document the new setup: env vars (`DATABASE_URL`, `ADMIN_TOKEN`, `YOUTUBE_API_KEY`, `YOUTUBE_PLAYLIST_ID`, `PUBLIC_URL`), the local-dev Postgres (Docker one-liner), running the test suite (needs Postgres), applying schema via `scripts/init_db.py`, and deploying to Vercel. Note the Supabase free-tier idle-pause behavior (first request after ~7 days wakes the DB, a few seconds) and Vercel cold starts (~1–3s) as expected, acceptable behavior.

- [ ] **Step 2 (optional): Remove Railway leftovers**

If keeping the repo Vercel-only, delete `Procfile` and `railway.toml`:
```bash
git rm Procfile railway.toml
```
Local dev still works via `uvicorn app.main:app --reload`. Skip this step if you want to keep Railway as a fallback.

- [ ] **Step 3: Final full-suite run**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document Vercel + Supabase setup and local dev"
```

---

## Phase 1 done — definition of complete

- `pytest -q` passes against a Postgres test database (DB tests skip cleanly when none is present).
- The app runs on Vercel, backed by Supabase Postgres, with anonymous name-prompt identity unchanged.
- Phone and TV reflect each other's changes within ~4s via polling; no SSE remains anywhere (`grep` is clean).
- `scripts/init_db.py` applies `schema.sql` + seeds quick-adds; no DDL or seeding runs on request.
- The QR code encodes the Vercel domain.

Phase 2 (Google `@nexite.io` sign-in) is a separate plan, written after Phase 1 ships.
