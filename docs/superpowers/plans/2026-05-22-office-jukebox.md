# Office Jukebox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LAN-only office "jukebox" web app. Coworkers paste YouTube links and upvote from their phones over office WiFi; a central screen shows a live leaderboard and plays the host-triggered top 4 via the YouTube IFrame Player.

**Architecture:** Single Python FastAPI process serves a tiny REST + SSE API and two static HTML pages (phone view and jukebox view). SQLite file for all state. YouTube IFrame Player API drives playback in the browser. Server-Sent Events push live leaderboard changes; phones also fall back to polling every 10s.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, stdlib `sqlite3`, `httpx`, `sse-starlette`, `qrcode[pil]`, `python-dotenv`, pytest, pytest-asyncio, pytest-httpx.

**Spec:** [docs/superpowers/specs/2026-05-22-office-jukebox-design.md](../specs/2026-05-22-office-jukebox-design.md)

---

## File Structure

```
office-jukebox/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + route wiring
│   ├── db.py                # SQLite connection + schema
│   ├── youtube.py           # URL parsing + oEmbed client
│   ├── events.py            # SSE pub/sub broker
│   ├── identity.py          # X-Voter-Id / X-Display-Name helpers
│   ├── admin.py             # Admin token check
│   ├── seed_data.py         # Curated quick-add seed list
│   └── static/
│       ├── index.html       # Phone view
│       ├── jukebox.html     # Jukebox view
│       ├── phone.js
│       ├── jukebox.js
│       └── styles.css
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_youtube.py
    ├── test_db.py
    ├── test_songs_api.py
    ├── test_votes_api.py
    ├── test_admin_api.py
    └── test_events.py
```

Each `app/*.py` file has one focused responsibility — adding behavior usually means editing one file, not several. Static frontend files are kept thin; the two `.js` files only handle their respective surface.

---

## Task 1: Project scaffolding

Set up the project skeleton: directory layout, dependencies, git, and a "hello world" FastAPI app you can start.

**Files:**
- Create: `office-jukebox/.gitignore`
- Create: `office-jukebox/.env.example`
- Create: `office-jukebox/requirements.txt`
- Create: `office-jukebox/app/__init__.py` (empty)
- Create: `office-jukebox/app/main.py`
- Create: `office-jukebox/tests/__init__.py` (empty)
- Create: `office-jukebox/tests/conftest.py`

- [ ] **Step 1: Initialize git in the project directory**

```bash
cd /Users/zvikag/office-jukebox
git init
git add docs/
git commit -m "chore: import design spec"
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
venv/
.env
*.db
*.sqlite
*.sqlite3
.pytest_cache/
.DS_Store
```

- [ ] **Step 3: Create `.env.example`**

```
ADMIN_TOKEN=change-me
PORT=8000
PUBLIC_URL=http://localhost:8000
DB_PATH=jukebox.db
```

- [ ] **Step 4: Create `requirements.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.27
httpx>=0.27
sse-starlette>=2.0
qrcode[pil]>=7.4
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-httpx>=0.30
```

- [ ] **Step 5: Create a virtualenv and install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 6: Create `app/main.py` with a minimal FastAPI app**

```python
from fastapi import FastAPI

app = FastAPI(title="Office Jukebox")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Create `tests/conftest.py` with a TestClient fixture**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 8: Write a smoke test for the health endpoint**

Create `tests/test_health.py`:

```python
def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 9: Run the test and confirm it passes**

Run: `pytest tests/test_health.py -v`
Expected: 1 passed

- [ ] **Step 10: Commit**

```bash
git add .gitignore .env.example requirements.txt app/ tests/
git commit -m "feat: scaffold FastAPI project with health endpoint"
```

---

## Task 2: YouTube URL parser

Pure function that extracts the 11-character video id from any common YouTube URL shape. No network calls, no state — ideal for TDD.

**Files:**
- Create: `app/youtube.py`
- Create: `tests/test_youtube.py`

- [ ] **Step 1: Write failing tests for URL parsing**

Create `tests/test_youtube.py`:

```python
import pytest

from app.youtube import extract_video_id


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
            "dQw4w9WgXcQ",
        ),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
        (
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
        ),
    ],
)
def test_extract_video_id_valid(url, expected):
    assert extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/",
        "https://youtu.be/",
        "https://www.youtube.com/playlist?list=PL123",
    ],
)
def test_extract_video_id_invalid(url):
    assert extract_video_id(url) is None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest tests/test_youtube.py -v`
Expected: ImportError (`app.youtube` doesn't exist yet)

- [ ] **Step 3: Implement `extract_video_id` in `app/youtube.py`**

```python
import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def extract_video_id(url: str) -> str | None:
    """Return the 11-char YouTube video id from any common URL shape, or None."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        return None

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]
    else:
        if parsed.path.rstrip("/") not in ("/watch", ""):
            return None
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]

    return candidate if _VIDEO_ID_RE.match(candidate) else None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/test_youtube.py -v`
Expected: all parametrized cases pass

- [ ] **Step 5: Commit**

```bash
git add app/youtube.py tests/test_youtube.py
git commit -m "feat(youtube): extract video id from common URL shapes"
```

---

## Task 3: YouTube oEmbed client

Add a function that fetches a video's title and thumbnail via YouTube's public oEmbed endpoint. Returns a fallback object on network failure (per the spec).

**Files:**
- Modify: `app/youtube.py`
- Modify: `tests/test_youtube.py`

- [ ] **Step 1: Add failing tests for `fetch_video_metadata`**

Append to `tests/test_youtube.py`:

```python
from app.youtube import VideoMetadata, fetch_video_metadata


def test_fetch_video_metadata_success(httpx_mock):
    httpx_mock.add_response(
        url="https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ&format=json",
        json={
            "title": "Rick Astley - Never Gonna Give You Up",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        },
    )
    meta = fetch_video_metadata("dQw4w9WgXcQ")
    assert meta == VideoMetadata(
        title="Rick Astley - Never Gonna Give You Up",
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    )


def test_fetch_video_metadata_network_error_falls_back(httpx_mock):
    import httpx

    httpx_mock.add_exception(httpx.ConnectError("boom"))
    meta = fetch_video_metadata("dQw4w9WgXcQ")
    assert meta.title == "Unknown title"
    assert meta.thumbnail_url.endswith("/hqdefault.jpg")


def test_fetch_video_metadata_404_falls_back(httpx_mock):
    httpx_mock.add_response(status_code=404)
    meta = fetch_video_metadata("dQw4w9WgXcQ")
    assert meta.title == "Unknown title"
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_youtube.py -v`
Expected: ImportError on `VideoMetadata` / `fetch_video_metadata`

- [ ] **Step 3: Implement the oEmbed client in `app/youtube.py`**

Append to `app/youtube.py`:

```python
from dataclasses import dataclass

import httpx

_OEMBED_URL = "https://www.youtube.com/oembed"
_DEFAULT_THUMB = "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    thumbnail_url: str


def fetch_video_metadata(video_id: str) -> VideoMetadata:
    """Look up title + thumbnail. Falls back to a default object on any failure."""
    fallback = VideoMetadata(
        title="Unknown title",
        thumbnail_url=_DEFAULT_THUMB.format(video_id=video_id),
    )
    target = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = httpx.get(
            _OEMBED_URL,
            params={"url": target, "format": "json"},
            timeout=5.0,
        )
        if response.status_code != 200:
            return fallback
        payload = response.json()
        return VideoMetadata(
            title=payload.get("title") or fallback.title,
            thumbnail_url=payload.get("thumbnail_url") or fallback.thumbnail_url,
        )
    except (httpx.HTTPError, ValueError):
        return fallback
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_youtube.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/youtube.py tests/test_youtube.py
git commit -m "feat(youtube): oEmbed client with graceful fallback"
```

---

## Task 4: Database schema + connection helper

Set up SQLite: a small helper for connections, a schema initializer for the three tables (`songs`, `votes`, `quick_adds`), and per-test isolation via an in-memory DB.

**Files:**
- Create: `app/db.py`
- Create: `tests/test_db.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for schema initialization**

Create `tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_db.py -v`
Expected: ImportError on `app.db`

- [ ] **Step 3: Implement `app/db.py`**

```python
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
```

- [ ] **Step 4: Update `tests/conftest.py` to use an in-memory DB per test**

Replace `tests/conftest.py`:

```python
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import init_schema, set_connection_for_tests
from app.main import app


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    set_connection_for_tests(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db) -> TestClient:
    return TestClient(app)
```

- [ ] **Step 5: Run tests and confirm they pass**

Run: `pytest tests/test_db.py tests/test_health.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_db.py tests/conftest.py
git commit -m "feat(db): SQLite schema + per-test in-memory connection"
```

---

## Task 5: Seed quick-adds + `GET /api/quick-adds`

Define the curated decade-spanning seed list, populate `quick_adds` on startup, and expose `GET /api/quick-adds` returning all of them grouped by decade.

**Files:**
- Create: `app/seed_data.py`
- Modify: `app/main.py`
- Create: `tests/test_quick_adds_api.py`

- [ ] **Step 1: Create the seed list in `app/seed_data.py`**

```python
"""Curated quick-add YouTube songs grouped by decade."""

QUICK_ADDS: list[dict[str, str]] = [
    # 60s
    {"youtube_id": "naQr0uTrH_s", "title": "The Beatles - Hey Jude", "decade": "60s"},
    {"youtube_id": "PGNiXGX2nLU", "title": "Rolling Stones - Satisfaction", "decade": "60s"},
    {"youtube_id": "iYYRH4apXDo", "title": "Aretha Franklin - Respect", "decade": "60s"},
    {"youtube_id": "Mb3iPP-tHdA", "title": "The Doors - Light My Fire", "decade": "60s"},
    {"youtube_id": "Q3dvbM6Pias", "title": "Sam & Dave - Soul Man", "decade": "60s"},
    # 70s
    {"youtube_id": "fJ9rUzIMcZQ", "title": "Queen - Bohemian Rhapsody", "decade": "70s"},
    {"youtube_id": "iPwM_kLJqLY", "title": "Stevie Wonder - Superstition", "decade": "70s"},
    {"youtube_id": "BciS5krYL80", "title": "Eagles - Hotel California", "decade": "70s"},
    {"youtube_id": "9EcjWd-O4jI", "title": "Earth, Wind & Fire - September", "decade": "70s"},
    {"youtube_id": "I_izvAbhExY", "title": "Bee Gees - Stayin' Alive", "decade": "70s"},
    # 80s
    {"youtube_id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up", "decade": "80s"},
    {"youtube_id": "btPJPFnesV4", "title": "Survivor - Eye of the Tiger", "decade": "80s"},
    {"youtube_id": "PIb6AZdTr-A", "title": "Toto - Africa", "decade": "80s"},
    {"youtube_id": "djV11Xbc914", "title": "a-ha - Take On Me", "decade": "80s"},
    {"youtube_id": "9jK-NcRmVcw", "title": "Journey - Don't Stop Believin'", "decade": "80s"},
    # 90s
    {"youtube_id": "hTWKbfoikeg", "title": "Nirvana - Smells Like Teen Spirit", "decade": "90s"},
    {"youtube_id": "fregObNcHC8", "title": "Backstreet Boys - I Want It That Way", "decade": "90s"},
    {"youtube_id": "gJLIiF15wjQ", "title": "Spice Girls - Wannabe", "decade": "90s"},
    {"youtube_id": "L_jWHffIx5E", "title": "Smash Mouth - All Star", "decade": "90s"},
    {"youtube_id": "K2cYWfq--Nw", "title": "Daft Punk - Around the World", "decade": "90s"},
    # 2000s
    {"youtube_id": "fLexgOxsZu0", "title": "OutKast - Hey Ya!", "decade": "2000s"},
    {"youtube_id": "y6120QOlsfU", "title": "Darude - Sandstorm", "decade": "2000s"},
    {"youtube_id": "-N4jf6rtyuw", "title": "Gnarls Barkley - Crazy", "decade": "2000s"},
    {"youtube_id": "60ItHLz5WEA", "title": "Coldplay - Viva La Vida", "decade": "2000s"},
    {"youtube_id": "fWNaR-rxAic", "title": "Black Eyed Peas - I Gotta Feeling", "decade": "2000s"},
    # 2010s
    {"youtube_id": "RgKAFK5djSk", "title": "Wiz Khalifa - See You Again", "decade": "2010s"},
    {"youtube_id": "kJQP7kiw5Fk", "title": "Luis Fonsi - Despacito", "decade": "2010s"},
    {"youtube_id": "JGwWNGJdvx8", "title": "Ed Sheeran - Shape of You", "decade": "2010s"},
    {"youtube_id": "OPf0YbXqDm0", "title": "Mark Ronson - Uptown Funk", "decade": "2010s"},
    {"youtube_id": "9bZkp7q19f0", "title": "PSY - Gangnam Style", "decade": "2010s"},
]


def thumbnail_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
```

> Note: YouTube video ids are best-effort; the implementer should sanity-check that each id still plays at runtime. The schema and behavior don't depend on the specific videos — bad ids surface as "Unknown title" via the oEmbed fallback but everything else still works.

- [ ] **Step 2: Write failing tests for the quick-adds endpoint**

Create `tests/test_quick_adds_api.py`:

```python
def test_quick_adds_returns_seeded_rows(client):
    response = client.get("/api/quick-adds")
    assert response.status_code == 200
    data = response.json()
    decades = {row["decade"] for row in data}
    assert decades == {"60s", "70s", "80s", "90s", "2000s", "2010s"}
    assert len(data) >= 30
    row = data[0]
    assert {"youtube_id", "title", "thumbnail_url", "decade"} <= row.keys()
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `pytest tests/test_quick_adds_api.py -v`
Expected: 404 (endpoint not wired yet)

- [ ] **Step 4: Wire the seed + endpoint in `app/main.py`**

Replace `app/main.py`:

```python
from fastapi import FastAPI

from app.db import get_connection, transaction
from app.seed_data import QUICK_ADDS, thumbnail_for

app = FastAPI(title="Office Jukebox")


def seed_quick_adds() -> None:
    with transaction() as conn:
        for entry in QUICK_ADDS:
            conn.execute(
                "INSERT OR IGNORE INTO quick_adds (youtube_id, title, thumbnail_url, decade) "
                "VALUES (?, ?, ?, ?)",
                (
                    entry["youtube_id"],
                    entry["title"],
                    thumbnail_for(entry["youtube_id"]),
                    entry["decade"],
                ),
            )


@app.on_event("startup")
def on_startup() -> None:
    get_connection()
    seed_quick_adds()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/quick-adds")
def list_quick_adds() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT youtube_id, title, thumbnail_url, decade FROM quick_adds ORDER BY decade, title"
    ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 5: Update `tests/conftest.py` so the in-memory DB is also seeded**

Replace `tests/conftest.py`:

```python
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
```

- [ ] **Step 6: Run tests and confirm they pass**

Run: `pytest tests/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add app/seed_data.py app/main.py tests/conftest.py tests/test_quick_adds_api.py
git commit -m "feat(quick-adds): seed curated list + GET /api/quick-adds"
```

---

## Task 6: Identity headers helper

A small FastAPI dependency that extracts `X-Voter-Id` and `X-Display-Name` from the request, with validation. Returns a typed object so endpoints don't repeat parsing logic.

**Files:**
- Create: `app/identity.py`
- Create: `tests/test_identity.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_identity.py`:

```python
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.identity import Identity, require_identity


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/who")
    def who(identity: Identity = Depends(require_identity)) -> dict[str, str]:
        return {"voter_id": identity.voter_id, "display_name": identity.display_name}

    return app


def test_identity_extracted_from_headers():
    client = TestClient(_build_app())
    response = client.get(
        "/who",
        headers={"X-Voter-Id": "v-123", "X-Display-Name": "Maya"},
    )
    assert response.status_code == 200
    assert response.json() == {"voter_id": "v-123", "display_name": "Maya"}


def test_identity_missing_voter_id_is_400():
    client = TestClient(_build_app())
    response = client.get("/who", headers={"X-Display-Name": "Maya"})
    assert response.status_code == 400


def test_identity_missing_display_name_is_400():
    client = TestClient(_build_app())
    response = client.get("/who", headers={"X-Voter-Id": "v-123"})
    assert response.status_code == 400


def test_identity_strips_whitespace_and_enforces_length():
    client = TestClient(_build_app())
    response = client.get(
        "/who",
        headers={"X-Voter-Id": "v-123", "X-Display-Name": "  " + ("a" * 40) + "  "},
    )
    # 40 chars allowed
    assert response.status_code == 200
    response = client.get(
        "/who",
        headers={"X-Voter-Id": "v-123", "X-Display-Name": "a" * 41},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_identity.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `app/identity.py`**

```python
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Identity:
    voter_id: str
    display_name: str


def require_identity(
    x_voter_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
) -> Identity:
    if not x_voter_id or not x_voter_id.strip():
        raise HTTPException(status_code=400, detail="X-Voter-Id header is required")
    name = (x_display_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="X-Display-Name header is required")
    if len(name) > 40:
        raise HTTPException(status_code=400, detail="display name too long (max 40 chars)")
    return Identity(voter_id=x_voter_id.strip(), display_name=name)
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_identity.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/identity.py tests/test_identity.py
git commit -m "feat(identity): voter-id + display-name header dependency"
```

---

## Task 7: `POST /api/songs` (add)

Add a song to today's list. Includes the duplicate → upvote-existing branch from the spec.

**Files:**
- Create: `tests/test_songs_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_songs_api.py`:

```python
import pytest


def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def test_add_song_success(client, httpx_mock):
    httpx_mock.add_response(
        json={
            "title": "Hotel California",
            "thumbnail_url": "https://example.com/t.jpg",
        }
    )
    response = client.post(
        "/api/songs",
        json={"youtube_url": "https://www.youtube.com/watch?v=BciS5krYL80"},
        headers=_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["youtube_id"] == "BciS5krYL80"
    assert body["title"] == "Hotel California"
    assert body["added_by_name"] == "Maya"


def test_add_song_invalid_url_returns_400(client):
    response = client.post(
        "/api/songs",
        json={"youtube_url": "https://example.com/foo"},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert "couldn't" in response.json()["detail"].lower() or "invalid" in response.json()["detail"].lower()


def test_add_duplicate_upvotes_existing(client, httpx_mock):
    httpx_mock.add_response(
        json={"title": "Hotel California", "thumbnail_url": "https://example.com/t.jpg"}
    )
    url = "https://www.youtube.com/watch?v=BciS5krYL80"
    first = client.post("/api/songs", json={"youtube_url": url}, headers=_headers("v-1"))
    assert first.status_code == 201
    first_id = first.json()["id"]

    # Different voter re-adds the same song
    second = client.post(
        "/api/songs",
        json={"youtube_url": url},
        headers=_headers("v-2", "Dan"),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["id"] == first_id
    assert body["already_in_list"] is True

    # Voter v-2's upvote should now exist
    listing = client.get("/api/songs", headers=_headers("v-2", "Dan")).json()
    matching = next(row for row in listing if row["id"] == first_id)
    assert matching["votes"] == 1
    assert matching["did_i_vote"] is True
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_songs_api.py -v`
Expected: 404 / route missing

- [ ] **Step 3: Add `POST /api/songs` to `app/main.py`**

Append imports and route to `app/main.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from app.identity import Identity, require_identity
from app.youtube import extract_video_id, fetch_video_metadata


class AddSongBody(BaseModel):
    youtube_url: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.post("/api/songs", status_code=201)
def add_song(
    body: AddSongBody,
    identity: Identity = Depends(require_identity),
) -> dict:
    video_id = extract_video_id(body.youtube_url)
    if not video_id:
        raise HTTPException(
            status_code=400,
            detail="couldn't recognize that YouTube link",
        )

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM songs WHERE youtube_id = ?", (video_id,)
    ).fetchone()

    if existing:
        song_id = existing["id"]
        with transaction() as tx:
            tx.execute(
                "INSERT OR IGNORE INTO votes (song_id, voter_id, created_at) VALUES (?, ?, ?)",
                (song_id, identity.voter_id, _now()),
            )
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=200,
            content={"id": song_id, "already_in_list": True},
        )

    meta = fetch_video_metadata(video_id)
    song_id = str(uuid.uuid4())
    with transaction() as tx:
        tx.execute(
            "INSERT INTO songs (id, youtube_id, title, thumbnail_url, duration_seconds, added_by_name, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (song_id, video_id, meta.title, meta.thumbnail_url, None, identity.display_name, _now()),
        )

    return {
        "id": song_id,
        "youtube_id": video_id,
        "title": meta.title,
        "thumbnail_url": meta.thumbnail_url,
        "added_by_name": identity.display_name,
        "already_in_list": False,
    }
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_songs_api.py::test_add_song_success tests/test_songs_api.py::test_add_song_invalid_url_returns_400 -v`
Expected: pass (the `test_add_duplicate_upvotes_existing` test depends on `GET /api/songs`, added next task; skip it for now or expect it to fail)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_songs_api.py
git commit -m "feat(songs): POST /api/songs with duplicate→upvote behavior"
```

---

## Task 8: `GET /api/songs` (list)

Return today's songs with vote counts and `did_i_vote` per the caller.

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: The test exists already** from Task 7 (`test_add_duplicate_upvotes_existing` calls `GET /api/songs`). Add one more dedicated test to `tests/test_songs_api.py`:

```python
def test_list_songs_sorted_by_votes_then_added_at(client, httpx_mock):
    httpx_mock.add_response(json={"title": "A", "thumbnail_url": "x"}, is_reusable=True)

    a = client.post(
        "/api/songs",
        json={"youtube_url": "https://youtu.be/aaaaaaaaaaa"},
        headers=_headers("v-1", "Maya"),
    ).json()
    b = client.post(
        "/api/songs",
        json={"youtube_url": "https://youtu.be/bbbbbbbbbbb"},
        headers=_headers("v-1", "Maya"),
    ).json()

    # Upvote b only
    client.post(f"/api/songs/{b['id']}/vote", headers=_headers("v-2", "Dan"))

    listing = client.get("/api/songs", headers=_headers("v-9", "Sam")).json()
    assert listing[0]["id"] == b["id"]
    assert listing[0]["votes"] == 1
    assert listing[1]["id"] == a["id"]
    assert listing[1]["votes"] == 0
    assert all(row["did_i_vote"] is False for row in listing)
```

- [ ] **Step 2: Run and confirm it fails**

Run: `pytest tests/test_songs_api.py::test_list_songs_sorted_by_votes_then_added_at -v`
Expected: 404 (route missing)

- [ ] **Step 3: Add `GET /api/songs` to `app/main.py`**

```python
@app.get("/api/songs")
def list_songs(identity: Identity = Depends(require_identity)) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            s.id, s.youtube_id, s.title, s.thumbnail_url, s.added_by_name, s.added_at,
            COUNT(v.voter_id) AS votes,
            SUM(CASE WHEN v.voter_id = ? THEN 1 ELSE 0 END) AS did_i_vote_count
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

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_songs_api.py -v`
Expected: all the listing + duplicate-upvote tests pass

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_songs_api.py
git commit -m "feat(songs): GET /api/songs with vote counts and did_i_vote"
```

---

## Task 9: `POST /api/songs/{id}/vote` (toggle)

Toggle the caller's vote on a song. Idempotent in effect (vote twice = no vote; third = vote again).

**Files:**
- Create: `tests/test_votes_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_votes_api.py`:

```python
def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def _add_song(client, httpx_mock, vid="aaaaaaaaaaa") -> str:
    httpx_mock.add_response(json={"title": "A", "thumbnail_url": "x"})
    response = client.post(
        "/api/songs",
        json={"youtube_url": f"https://youtu.be/{vid}"},
        headers=_headers(),
    )
    return response.json()["id"]


def test_vote_toggles_on_then_off(client, httpx_mock):
    song_id = _add_song(client, httpx_mock)
    voter = _headers("v-2", "Dan")

    response = client.post(f"/api/songs/{song_id}/vote", headers=voter)
    assert response.status_code == 200
    assert response.json() == {"id": song_id, "did_i_vote": True, "votes": 1}

    response = client.post(f"/api/songs/{song_id}/vote", headers=voter)
    assert response.status_code == 200
    assert response.json() == {"id": song_id, "did_i_vote": False, "votes": 0}


def test_vote_on_missing_song_404(client):
    response = client.post(
        "/api/songs/does-not-exist/vote", headers=_headers("v-2", "Dan")
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run and confirm fail**

Run: `pytest tests/test_votes_api.py -v`
Expected: 404 / route missing or wrong response

- [ ] **Step 3: Add the route to `app/main.py`**

```python
@app.post("/api/songs/{song_id}/vote")
def toggle_vote(
    song_id: str,
    identity: Identity = Depends(require_identity),
) -> dict:
    conn = get_connection()
    exists = conn.execute("SELECT 1 FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="song not found")

    with transaction() as tx:
        cur = tx.execute(
            "DELETE FROM votes WHERE song_id = ? AND voter_id = ?",
            (song_id, identity.voter_id),
        )
        if cur.rowcount == 0:
            tx.execute(
                "INSERT INTO votes (song_id, voter_id, created_at) VALUES (?, ?, ?)",
                (song_id, identity.voter_id, _now()),
            )
            did_i_vote = True
        else:
            did_i_vote = False

    votes = conn.execute(
        "SELECT COUNT(*) AS c FROM votes WHERE song_id = ?", (song_id,)
    ).fetchone()["c"]
    return {"id": song_id, "did_i_vote": did_i_vote, "votes": votes}
```

- [ ] **Step 4: Run and confirm pass**

Run: `pytest tests/test_votes_api.py -v`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_votes_api.py
git commit -m "feat(votes): toggle vote endpoint"
```

---

## Task 10: Admin token dependency

A FastAPI dependency that checks the admin token from either an `X-Admin-Token` header or `?admin=` query param against the configured value.

**Files:**
- Create: `app/admin.py`
- Create: `tests/test_admin.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin.py`:

```python
import os

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.admin import require_admin


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.post("/secret")
    def secret(_: None = Depends(require_admin)) -> dict[str, bool]:
        return {"ok": True}

    return app


def test_admin_accepts_header(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    client = TestClient(_build_app())
    response = client.post("/secret", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200


def test_admin_accepts_query(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    client = TestClient(_build_app())
    response = client.post("/secret?admin=s3cret")
    assert response.status_code == 200


def test_admin_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    client = TestClient(_build_app())
    response = client.post("/secret", headers={"X-Admin-Token": "nope"})
    assert response.status_code == 403


def test_admin_rejects_when_no_token_configured(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    client = TestClient(_build_app())
    response = client.post("/secret", headers={"X-Admin-Token": "anything"})
    assert response.status_code == 500
```

- [ ] **Step 2: Run and confirm fail**

Run: `pytest tests/test_admin.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `app/admin.py`**

```python
import os

from fastapi import Header, HTTPException, Query


def require_admin(
    x_admin_token: str | None = Header(default=None),
    admin: str | None = Query(default=None),
) -> None:
    configured = os.environ.get("ADMIN_TOKEN")
    if not configured:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    provided = x_admin_token or admin
    if provided != configured:
        raise HTTPException(status_code=403, detail="admin token required")
```

- [ ] **Step 4: Run and confirm pass**

Run: `pytest tests/test_admin.py -v`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add app/admin.py tests/test_admin.py
git commit -m "feat(admin): admin token dependency"
```

---

## Task 11: `POST /api/play`

Admin-only endpoint that returns the top-4 song ids in order for the jukebox view to play.

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_admin_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin_api.py`:

```python
def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def _add(client, httpx_mock, vid: str):
    httpx_mock.add_response(json={"title": vid, "thumbnail_url": "x"})
    return client.post(
        "/api/songs",
        json={"youtube_url": f"https://youtu.be/{vid}"},
        headers=_headers(),
    ).json()["id"]


def test_play_returns_top4_in_vote_order(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    ids = [_add(client, httpx_mock, f"vid{i:08d}aaa"[:11]) for i in range(5)]
    # Give them descending votes: ids[0]=4, [1]=3, [2]=2, [3]=1, [4]=0
    for i, sid in enumerate(ids):
        for v in range(4 - i):
            client.post(
                f"/api/songs/{sid}/vote",
                headers={"X-Voter-Id": f"voter-{i}-{v}", "X-Display-Name": "X"},
            )

    response = client.post("/api/play", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["queue"]] == ids[:4]
    assert body["queue"][0]["youtube_id"]


def test_play_requires_admin(client):
    response = client.post("/api/play")
    assert response.status_code in (403, 500)


def test_play_empty_returns_empty_queue(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    response = client.post("/api/play", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    assert response.json() == {"queue": []}
```

- [ ] **Step 2: Run and confirm fail**

Run: `pytest tests/test_admin_api.py -v`
Expected: 404

- [ ] **Step 3: Add `POST /api/play` to `app/main.py`**

```python
from app.admin import require_admin


@app.post("/api/play")
def play(_: None = Depends(require_admin)) -> dict:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT s.id, s.youtube_id, s.title, s.thumbnail_url,
               COUNT(v.voter_id) AS votes
        FROM songs s
        LEFT JOIN votes v ON v.song_id = s.id
        GROUP BY s.id
        ORDER BY votes DESC, s.added_at ASC
        LIMIT 4
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

- [ ] **Step 4: Run and confirm pass**

Run: `pytest tests/test_admin_api.py -v`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_admin_api.py
git commit -m "feat(play): POST /api/play returns top 4 in vote order"
```

---

## Task 12: `POST /api/reset`

Admin-only endpoint that wipes `songs` (cascades to `votes`).

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_admin_api.py`

- [ ] **Step 1: Append failing tests to `tests/test_admin_api.py`**

```python
def test_reset_wipes_songs_and_votes(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    sid = _add(client, httpx_mock, "vid00000000")
    client.post(
        f"/api/songs/{sid}/vote",
        headers={"X-Voter-Id": "v-x", "X-Display-Name": "X"},
    )

    response = client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})
    assert response.status_code == 200
    assert response.json() == {"deleted_songs": 1, "deleted_votes": 1}

    listing = client.get("/api/songs", headers=_headers()).json()
    assert listing == []


def test_reset_requires_admin(client):
    response = client.post("/api/reset")
    assert response.status_code in (403, 500)
```

- [ ] **Step 2: Run and confirm fail**

Run: `pytest tests/test_admin_api.py::test_reset_wipes_songs_and_votes -v`
Expected: 404

- [ ] **Step 3: Add `POST /api/reset` to `app/main.py`**

```python
@app.post("/api/reset")
def reset_day(_: None = Depends(require_admin)) -> dict[str, int]:
    with transaction() as tx:
        votes_cur = tx.execute("DELETE FROM votes")
        songs_cur = tx.execute("DELETE FROM songs")
    return {
        "deleted_songs": songs_cur.rowcount,
        "deleted_votes": votes_cur.rowcount,
    }
```

- [ ] **Step 4: Run and confirm pass**

Run: `pytest tests/test_admin_api.py -v`
Expected: pass

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_admin_api.py
git commit -m "feat(reset): POST /api/reset wipes day"
```

---

## Task 13: SSE event stream

A simple in-process pub/sub. After every add / vote / reset, the API publishes a `songs_changed` event; `GET /api/events` streams them to listening clients via SSE.

**Files:**
- Create: `app/events.py`
- Create: `tests/test_events.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_events.py`:

```python
import asyncio

import pytest

from app.events import EventBroker


@pytest.mark.asyncio
async def test_broker_delivers_to_subscriber():
    broker = EventBroker()
    async with broker.subscribe() as queue:
        await broker.publish("songs_changed")
        message = await asyncio.wait_for(queue.get(), timeout=0.5)
        assert message == "songs_changed"


@pytest.mark.asyncio
async def test_broker_delivers_to_multiple_subscribers():
    broker = EventBroker()
    async with broker.subscribe() as q1, broker.subscribe() as q2:
        await broker.publish("songs_changed")
        m1 = await asyncio.wait_for(q1.get(), timeout=0.5)
        m2 = await asyncio.wait_for(q2.get(), timeout=0.5)
        assert m1 == m2 == "songs_changed"


def test_events_endpoint_emits_after_add(client, httpx_mock):
    # Open an SSE stream, write a song, expect at least one event line.
    httpx_mock.add_response(json={"title": "A", "thumbnail_url": "x"})
    with client.stream("GET", "/api/events") as stream:
        # Trigger an add concurrently via a side-channel client.
        import threading

        def add():
            client.post(
                "/api/songs",
                json={"youtube_url": "https://youtu.be/aaaaaaaaaaa"},
                headers={"X-Voter-Id": "v-1", "X-Display-Name": "Maya"},
            )

        threading.Thread(target=add).start()
        chunks = []
        for chunk in stream.iter_lines():
            if chunk:
                chunks.append(chunk)
                if "songs_changed" in chunk:
                    break
        assert any("songs_changed" in c for c in chunks)
```

- [ ] **Step 2: Run and confirm fail**

Run: `pytest tests/test_events.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `app/events.py`**

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class EventBroker:
    """Tiny in-process pub/sub for SSE."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event: str) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer; drop


broker = EventBroker()


def publish_sync(event: str) -> None:
    """Call from sync code (FastAPI route handlers) — schedules on the running loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop.is_running():
        loop.create_task(broker.publish(event))
    else:
        loop.run_until_complete(broker.publish(event))
```

- [ ] **Step 4: Wire the SSE endpoint and publish on writes — modify `app/main.py`**

Add near the top:

```python
from sse_starlette.sse import EventSourceResponse

from app.events import broker, publish_sync
```

Add the route:

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

In `add_song`, `toggle_vote`, and `reset_day` — at the end of each successful path, call:

```python
publish_sync("songs_changed")
```

For `add_song`, publish on both branches (new and duplicate→upvote). For `toggle_vote`, publish after vote count is computed. For `reset_day`, publish after the wipe.

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: all pass. The SSE integration test (`test_events_endpoint_emits_after_add`) can be skipped on CI if it proves flaky in `TestClient`; mark with `@pytest.mark.skip(reason="flaky under TestClient")` if so.

- [ ] **Step 6: Commit**

```bash
git add app/events.py tests/test_events.py app/main.py
git commit -m "feat(events): SSE stream + publish on add/vote/reset"
```

---

## Task 14: Static files mount + QR code helper + jukebox idle view

Set up `app/static/` as a mount, add a QR-code endpoint, and write the jukebox HTML in its idle (no-player) form: header with QR + URL, podium of top 4, scrolling list of the rest. Live updates via SSE.

**Files:**
- Create: `app/static/styles.css`
- Create: `app/static/jukebox.html`
- Create: `app/static/jukebox.js`
- Modify: `app/main.py`

- [ ] **Step 1: Mount `app/static/` and add a QR endpoint — modify `app/main.py`**

Add near the top:

```python
import io
import os

import qrcode
from fastapi import Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
```

After all routes are defined, add:

```python
@app.get("/api/qrcode.png")
def qrcode_png() -> Response:
    public_url = os.environ.get("PUBLIC_URL", "http://localhost:8000")
    img = qrcode.make(public_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/jukebox")
def jukebox_page() -> FileResponse:
    return FileResponse("app/static/jukebox.html")


@app.get("/")
def root_page() -> FileResponse:
    return FileResponse("app/static/index.html")


app.mount("/static", StaticFiles(directory="app/static"), name="static")
```

- [ ] **Step 2: Create `app/static/styles.css`**

```css
:root {
    --bg: #0d1117;
    --fg: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --podium: #f1c40f;
    --card: #161b22;
}

* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--fg); }

.jukebox { padding: 24px; max-width: 1400px; margin: 0 auto; }
.jukebox h1 { font-size: 2rem; margin: 0 0 16px; }
.jukebox-header { display: flex; gap: 24px; align-items: center; margin-bottom: 24px; }
.jukebox-header .qr { background: white; padding: 12px; border-radius: 12px; }
.jukebox-header .url { font-family: monospace; font-size: 1.25rem; color: var(--accent); }

.podium { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
.podium .card { background: var(--card); padding: 12px; border-radius: 12px; border: 2px solid var(--podium); }
.podium .card img { width: 100%; border-radius: 8px; }
.podium .card .votes { font-size: 1.5rem; font-weight: bold; color: var(--podium); }

.song-list { display: flex; flex-direction: column; gap: 8px; }
.song-list .row { display: flex; gap: 12px; align-items: center; background: var(--card); padding: 8px; border-radius: 8px; }
.song-list .row img { width: 96px; border-radius: 4px; }
.song-list .row .meta { flex: 1; }
.song-list .row .votes { font-size: 1.25rem; font-weight: bold; }

.admin-actions { position: fixed; bottom: 24px; right: 24px; display: flex; gap: 12px; }
.admin-actions button { padding: 12px 24px; font-size: 1rem; border-radius: 8px; border: none; cursor: pointer; }
.btn-play { background: var(--accent); color: white; }
.btn-reset { background: #c9302c; color: white; }

#player { position: fixed; inset: 0; background: black; z-index: 100; display: none; }
#player.active { display: block; }
#player iframe { width: 100%; height: 100%; border: 0; }
#player .now-playing { position: absolute; bottom: 32px; left: 32px; background: rgba(0,0,0,0.7); padding: 16px 24px; border-radius: 8px; font-size: 1.5rem; }
```

- [ ] **Step 3: Create `app/static/jukebox.html`**

```html
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Office Jukebox</title>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
    <div class="jukebox">
        <div class="jukebox-header">
            <img class="qr" src="/api/qrcode.png" alt="Scan to join" width="180" height="180">
            <div>
                <h1>🎵 Office Jukebox</h1>
                <div class="url" id="public-url">Loading…</div>
                <div class="muted">Scan the QR or open the URL on your phone to add a song.</div>
            </div>
        </div>

        <div class="podium" id="podium"></div>
        <div class="song-list" id="rest"></div>

        <div class="admin-actions" id="admin-actions" hidden>
            <button class="btn-play" id="btn-play">▶ Play top 4</button>
            <button class="btn-reset" id="btn-reset">↺ Reset for tomorrow</button>
        </div>

        <div id="player">
            <iframe id="yt-iframe" allow="autoplay; encrypted-media"></iframe>
            <div class="now-playing" id="now-playing"></div>
        </div>
    </div>
    <script src="/static/jukebox.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create `app/static/jukebox.js` — idle/list rendering + SSE only (player added next task)**

```javascript
const params = new URLSearchParams(location.search);
const adminToken = params.get("admin");

// Jukebox view doesn't vote, but the GET /api/songs endpoint requires identity headers.
const identityHeaders = {
    "X-Voter-Id": "jukebox-screen",
    "X-Display-Name": "Jukebox",
};

async function fetchSongs() {
    const response = await fetch("/api/songs", { headers: identityHeaders });
    return response.json();
}

function thumb(url) {
    const img = document.createElement("img");
    img.src = url;
    img.loading = "lazy";
    return img;
}

function renderPodium(songs) {
    const container = document.getElementById("podium");
    container.innerHTML = "";
    songs.slice(0, 4).forEach((song, i) => {
        const card = document.createElement("div");
        card.className = "card";
        card.appendChild(thumb(song.thumbnail_url));
        const title = document.createElement("div");
        title.textContent = `#${i + 1} ${song.title}`;
        card.appendChild(title);
        const meta = document.createElement("div");
        meta.className = "muted";
        meta.textContent = `added by ${song.added_by_name}`;
        card.appendChild(meta);
        const votes = document.createElement("div");
        votes.className = "votes";
        votes.textContent = `${song.votes} ❤`;
        card.appendChild(votes);
        container.appendChild(card);
    });
}

function renderRest(songs) {
    const container = document.getElementById("rest");
    container.innerHTML = "";
    songs.slice(4).forEach((song) => {
        const row = document.createElement("div");
        row.className = "row";
        row.appendChild(thumb(song.thumbnail_url));
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.innerHTML = `<div>${song.title}</div><div class="muted">added by ${song.added_by_name}</div>`;
        row.appendChild(meta);
        const votes = document.createElement("div");
        votes.className = "votes";
        votes.textContent = `${song.votes} ❤`;
        row.appendChild(votes);
        container.appendChild(row);
    });
}

async function refresh() {
    const songs = await fetchSongs();
    renderPodium(songs);
    renderRest(songs);
}

function setupAdmin() {
    if (!adminToken) return;
    document.getElementById("admin-actions").hidden = false;
    document.getElementById("btn-reset").addEventListener("click", async () => {
        if (!confirm("Wipe all songs and votes for today?")) return;
        await fetch(`/api/reset?admin=${encodeURIComponent(adminToken)}`, { method: "POST" });
    });
}

function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", refresh);
}

document.getElementById("public-url").textContent = location.origin;
setupAdmin();
setupSSE();
refresh();
```

- [ ] **Step 5: Manual smoke**

```bash
ADMIN_TOKEN=test PUBLIC_URL="http://localhost:8000" .venv/bin/uvicorn app.main:app --reload
```

Visit:
- `http://localhost:8000/jukebox` — should show the QR + empty podium/list.
- `http://localhost:8000/jukebox?admin=test` — should additionally show Play/Reset buttons.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/static/styles.css app/static/jukebox.html app/static/jukebox.js
git commit -m "feat(jukebox): idle view with QR, podium, list, SSE refresh"
```

---

## Task 15: Jukebox view — YouTube IFrame player + auto-advance

Add the play-mode behavior: when admin clicks Play, fetch the queue, load the YouTube IFrame Player API, play each video in sequence, return to idle when done. Handle embed errors by skipping. Add Skip and Stop admin controls during playback.

**Files:**
- Modify: `app/static/jukebox.html` (add YT IFrame API script)
- Modify: `app/static/jukebox.js`

- [ ] **Step 1: Add the YouTube IFrame API to `jukebox.html`**

Inside `<head>` add:

```html
<script src="https://www.youtube.com/iframe_api"></script>
```

Also add Skip + Stop buttons inside `#player`:

```html
<div id="player">
    <div id="yt-target"></div>
    <div class="now-playing" id="now-playing"></div>
    <div class="admin-actions" id="player-actions" hidden>
        <button class="btn-play" id="btn-skip">⏭ Skip</button>
        <button class="btn-reset" id="btn-stop">■ Stop</button>
    </div>
</div>
```

Remove the previous `<iframe id="yt-iframe">` element — the IFrame API will inject its own iframe into `#yt-target`.

- [ ] **Step 2: Replace `jukebox.js` to add playback logic**

Replace the whole file with:

```javascript
const params = new URLSearchParams(location.search);
const adminToken = params.get("admin");

const identityHeaders = {
    "X-Voter-Id": "jukebox-screen",
    "X-Display-Name": "Jukebox",
};

let ytPlayer = null;
let queue = [];
let queueIndex = 0;

async function fetchSongs() {
    const response = await fetch("/api/songs", { headers: identityHeaders });
    return response.json();
}

function thumb(url) {
    const img = document.createElement("img");
    img.src = url;
    img.loading = "lazy";
    return img;
}

function renderPodium(songs) {
    const container = document.getElementById("podium");
    container.innerHTML = "";
    songs.slice(0, 4).forEach((song, i) => {
        const card = document.createElement("div");
        card.className = "card";
        card.appendChild(thumb(song.thumbnail_url));
        const title = document.createElement("div");
        title.textContent = `#${i + 1} ${song.title}`;
        card.appendChild(title);
        const meta = document.createElement("div");
        meta.className = "muted";
        meta.textContent = `added by ${song.added_by_name}`;
        card.appendChild(meta);
        const votes = document.createElement("div");
        votes.className = "votes";
        votes.textContent = `${song.votes} ❤`;
        card.appendChild(votes);
        container.appendChild(card);
    });
}

function renderRest(songs) {
    const container = document.getElementById("rest");
    container.innerHTML = "";
    songs.slice(4).forEach((song) => {
        const row = document.createElement("div");
        row.className = "row";
        row.appendChild(thumb(song.thumbnail_url));
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.innerHTML = `<div>${song.title}</div><div class="muted">added by ${song.added_by_name}</div>`;
        row.appendChild(meta);
        const votes = document.createElement("div");
        votes.className = "votes";
        votes.textContent = `${song.votes} ❤`;
        row.appendChild(votes);
        container.appendChild(row);
    });
}

async function refresh() {
    const songs = await fetchSongs();
    renderPodium(songs);
    renderRest(songs);
}

function showPlayer(on) {
    document.getElementById("player").classList.toggle("active", on);
    document.getElementById("player-actions").hidden = !on || !adminToken;
}

function playCurrent() {
    if (queueIndex >= queue.length) {
        stopPlayback();
        return;
    }
    const song = queue[queueIndex];
    document.getElementById("now-playing").textContent =
        `▶ ${song.title}  (${queueIndex + 1}/${queue.length})`;
    ytPlayer.loadVideoById(song.youtube_id);
}

function advance() {
    queueIndex += 1;
    playCurrent();
}

function stopPlayback() {
    if (ytPlayer && ytPlayer.stopVideo) ytPlayer.stopVideo();
    showPlayer(false);
    queue = [];
    queueIndex = 0;
}

function showToast(message) {
    const toast = document.createElement("div");
    toast.textContent = message;
    toast.style.cssText =
        "position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#c9302c;color:white;padding:12px 24px;border-radius:8px;z-index:200;";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

window.onYouTubeIframeAPIReady = function () {
    ytPlayer = new YT.Player("yt-target", {
        width: "100%",
        height: "100%",
        playerVars: { autoplay: 1, controls: 0, modestbranding: 1 },
        events: {
            onStateChange: (e) => {
                if (e.data === YT.PlayerState.ENDED) advance();
            },
            onError: () => {
                showToast("⚠️ couldn't play that one — skipping");
                advance();
            },
        },
    });
};

async function startPlayback() {
    if (!adminToken) return;
    const response = await fetch(`/api/play?admin=${encodeURIComponent(adminToken)}`, {
        method: "POST",
    });
    if (!response.ok) return;
    const body = await response.json();
    if (body.queue.length === 0) return;
    queue = body.queue;
    queueIndex = 0;
    showPlayer(true);
    playCurrent();
}

function setupAdmin() {
    if (!adminToken) return;
    document.getElementById("admin-actions").hidden = false;
    document.getElementById("btn-play").addEventListener("click", startPlayback);
    document.getElementById("btn-reset").addEventListener("click", async () => {
        if (!confirm("Wipe all songs and votes for today?")) return;
        await fetch(`/api/reset?admin=${encodeURIComponent(adminToken)}`, { method: "POST" });
    });
    document.getElementById("btn-skip").addEventListener("click", advance);
    document.getElementById("btn-stop").addEventListener("click", stopPlayback);
}

function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", refresh);
}

document.getElementById("public-url").textContent = location.origin;
setupAdmin();
setupSSE();
refresh();
```

- [ ] **Step 3: Manual smoke**

```bash
ADMIN_TOKEN=test PUBLIC_URL="http://localhost:8000" .venv/bin/uvicorn app.main:app --reload
```

In one browser:
1. Open `http://localhost:8000/?` and add 4 songs (use phone view — built next task — or `curl`).
2. Open `http://localhost:8000/jukebox?admin=test` in another tab.
3. Click "Play top 4". Confirm each video plays in sequence and auto-advances on end.
4. Click Skip mid-song — confirm next video starts.
5. Click Stop — confirm return to idle.

- [ ] **Step 4: Commit**

```bash
git add app/static/jukebox.html app/static/jukebox.js
git commit -m "feat(jukebox): YouTube IFrame player with auto-advance + admin skip/stop"
```

---

## Task 16: Phone view (HTML + JS)

The phone surface: name prompt, paste-URL input, decade chips with expandable quick-add lists, live song list with toggleable upvotes, SSE refresh with 10s polling fallback.

**Files:**
- Create: `app/static/index.html`
- Create: `app/static/phone.js`

- [ ] **Step 1: Create `app/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Office Jukebox</title>
    <link rel="stylesheet" href="/static/styles.css">
    <style>
        body { padding: 16px; max-width: 600px; margin: 0 auto; }
        .name-prompt { background: var(--card); padding: 24px; border-radius: 12px; }
        .name-prompt input { width: 100%; padding: 12px; font-size: 1.25rem; border-radius: 8px; border: 1px solid #555; background: #222; color: var(--fg); }
        .name-prompt button { padding: 12px 24px; margin-top: 12px; border-radius: 8px; border: none; background: var(--accent); color: white; font-size: 1rem; }
        .add-row { display: flex; gap: 8px; margin: 16px 0; }
        .add-row input { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #555; background: #222; color: var(--fg); }
        .add-row button { padding: 12px 16px; border-radius: 8px; border: none; background: var(--accent); color: white; }
        .decade-row { display: flex; gap: 8px; overflow-x: auto; margin-bottom: 12px; }
        .decade-row .chip { padding: 8px 16px; border-radius: 999px; background: var(--card); cursor: pointer; white-space: nowrap; }
        .decade-row .chip.active { background: var(--accent); color: white; }
        .quick-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; margin-bottom: 16px; }
        .quick-list .card { background: var(--card); padding: 8px; border-radius: 8px; cursor: pointer; text-align: center; font-size: 0.85rem; }
        .quick-list .card img { width: 100%; border-radius: 4px; }
        .song-card { display: flex; gap: 12px; align-items: center; background: var(--card); padding: 12px; border-radius: 8px; margin-bottom: 8px; }
        .song-card.top4 { border-left: 4px solid var(--podium); }
        .song-card img { width: 80px; border-radius: 4px; }
        .song-card .meta { flex: 1; min-width: 0; }
        .song-card .title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
        .song-card .added-by { color: var(--muted); font-size: 0.85rem; }
        .vote-btn { padding: 12px; border-radius: 999px; border: none; background: transparent; color: var(--muted); font-size: 1.5rem; cursor: pointer; }
        .vote-btn.voted { color: #ff4d6d; }
        .message { padding: 12px; border-radius: 8px; margin: 8px 0; }
        .message.error { background: #c9302c33; color: #ff8e8e; }
        .message.info { background: #58a6ff33; color: var(--accent); }
    </style>
</head>
<body>
    <div id="name-prompt" class="name-prompt" hidden>
        <h2>What's your name?</h2>
        <input id="name-input" placeholder="Maya">
        <button id="name-submit">Join</button>
    </div>

    <div id="app" hidden>
        <h2>🎵 Today's Playlist</h2>
        <div class="muted">You are <span id="who-am-i"></span> · <a href="#" id="rename">change</a></div>

        <div class="add-row">
            <input id="url-input" placeholder="Paste a YouTube link…">
            <button id="url-submit">Add</button>
        </div>

        <div id="message-area"></div>

        <div class="decade-row" id="decade-row"></div>
        <div class="quick-list" id="quick-list"></div>

        <div id="song-list"></div>
    </div>

    <script src="/static/phone.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `app/static/phone.js`**

```javascript
const VOTER_KEY = "jukebox.voter_id";
const NAME_KEY = "jukebox.display_name";

function uuid() {
    return crypto.randomUUID();
}

function getVoterId() {
    let id = localStorage.getItem(VOTER_KEY);
    if (!id) {
        id = uuid();
        localStorage.setItem(VOTER_KEY, id);
    }
    return id;
}

function getDisplayName() {
    return localStorage.getItem(NAME_KEY) || "";
}

function setDisplayName(name) {
    localStorage.setItem(NAME_KEY, name);
}

function identityHeaders() {
    return {
        "X-Voter-Id": getVoterId(),
        "X-Display-Name": getDisplayName(),
        "Content-Type": "application/json",
    };
}

function showMessage(text, kind = "info") {
    const area = document.getElementById("message-area");
    const el = document.createElement("div");
    el.className = `message ${kind}`;
    el.textContent = text;
    area.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

async function loadSongs() {
    const response = await fetch("/api/songs", { headers: identityHeaders() });
    if (!response.ok) return;
    const songs = await response.json();
    renderSongs(songs);
}

function renderSongs(songs) {
    const container = document.getElementById("song-list");
    container.innerHTML = "";
    songs.forEach((song, i) => {
        const card = document.createElement("div");
        card.className = "song-card" + (i < 4 ? " top4" : "");
        const img = document.createElement("img");
        img.src = song.thumbnail_url;
        img.loading = "lazy";
        card.appendChild(img);
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.innerHTML = `
            <div class="title">${escapeHtml(song.title)}</div>
            <div class="added-by">added by ${escapeHtml(song.added_by_name)} · ${song.votes} ❤</div>
            ${i < 4 ? '<div class="muted">🏆 in the top 4</div>' : ""}
        `;
        card.appendChild(meta);
        const btn = document.createElement("button");
        btn.className = "vote-btn" + (song.did_i_vote ? " voted" : "");
        btn.textContent = song.did_i_vote ? "❤" : "🤍";
        btn.addEventListener("click", () => toggleVote(song.id));
        card.appendChild(btn);
        container.appendChild(card);
    });
}

function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[c]));
}

async function toggleVote(songId) {
    const response = await fetch(`/api/songs/${songId}/vote`, {
        method: "POST",
        headers: identityHeaders(),
    });
    if (!response.ok) return;
    await loadSongs();
}

async function addByUrl(url) {
    const response = await fetch("/api/songs", {
        method: "POST",
        headers: identityHeaders(),
        body: JSON.stringify({ youtube_url: url }),
    });
    if (response.status === 400) {
        const body = await response.json();
        showMessage(body.detail || "couldn't add that link", "error");
        return;
    }
    if (response.status === 200) {
        showMessage("already in the list — upvoted for you", "info");
    } else if (response.status === 201) {
        showMessage("added!", "info");
    }
    await loadSongs();
}

async function loadQuickAdds() {
    const response = await fetch("/api/quick-adds");
    if (!response.ok) return;
    const rows = await response.json();
    const decades = ["60s", "70s", "80s", "90s", "2000s", "2010s"];
    const byDecade = {};
    decades.forEach((d) => (byDecade[d] = []));
    rows.forEach((row) => byDecade[row.decade]?.push(row));

    const decadeRow = document.getElementById("decade-row");
    const quickList = document.getElementById("quick-list");
    let activeDecade = decades[0];

    function renderDecade() {
        decadeRow.innerHTML = "";
        decades.forEach((d) => {
            const chip = document.createElement("div");
            chip.className = "chip" + (d === activeDecade ? " active" : "");
            chip.textContent = d;
            chip.addEventListener("click", () => {
                activeDecade = d;
                renderDecade();
            });
            decadeRow.appendChild(chip);
        });
        quickList.innerHTML = "";
        byDecade[activeDecade].forEach((row) => {
            const card = document.createElement("div");
            card.className = "card";
            const img = document.createElement("img");
            img.src = row.thumbnail_url;
            card.appendChild(img);
            const title = document.createElement("div");
            title.textContent = row.title;
            card.appendChild(title);
            card.addEventListener("click", () =>
                addByUrl(`https://www.youtube.com/watch?v=${row.youtube_id}`)
            );
            quickList.appendChild(card);
        });
    }
    renderDecade();
}

function setupAddRow() {
    const input = document.getElementById("url-input");
    document.getElementById("url-submit").addEventListener("click", () => {
        const url = input.value.trim();
        if (url) {
            addByUrl(url);
            input.value = "";
        }
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") document.getElementById("url-submit").click();
    });
}

function setupRename() {
    document.getElementById("rename").addEventListener("click", (e) => {
        e.preventDefault();
        const name = prompt("New display name:", getDisplayName());
        if (name && name.trim()) {
            setDisplayName(name.trim());
            document.getElementById("who-am-i").textContent = name.trim();
        }
    });
}

function setupSSE() {
    const source = new EventSource("/api/events");
    source.addEventListener("songs_changed", loadSongs);
}

function startApp() {
    document.getElementById("name-prompt").hidden = true;
    document.getElementById("app").hidden = false;
    document.getElementById("who-am-i").textContent = getDisplayName();
    setupAddRow();
    setupRename();
    setupSSE();
    loadQuickAdds();
    loadSongs();
    setInterval(loadSongs, 10000); // polling fallback
}

function setupNamePrompt() {
    const submit = document.getElementById("name-submit");
    const input = document.getElementById("name-input");
    submit.addEventListener("click", () => {
        const name = input.value.trim();
        if (!name) return;
        setDisplayName(name);
        startApp();
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") submit.click();
    });
}

if (getDisplayName()) {
    startApp();
} else {
    document.getElementById("name-prompt").hidden = false;
    setupNamePrompt();
}
```

- [ ] **Step 3: Manual smoke**

```bash
ADMIN_TOKEN=test PUBLIC_URL="http://localhost:8000" .venv/bin/uvicorn app.main:app --reload
```

In a browser (use phone or DevTools mobile mode):
1. `http://localhost:8000/` → enter a name → see today's list.
2. Paste a YouTube link → see "added!" toast and new row appear.
3. Paste the same link again → see "already in the list — upvoted" + your vote toggled on.
4. Tap a decade chip → see quick-add cards → tap one → added.
5. Tap heart on a song → vote count changes immediately.
6. Open a second browser (different localStorage) → vote → see it appear here via SSE within ~1s.

- [ ] **Step 4: Commit**

```bash
git add app/static/index.html app/static/phone.js
git commit -m "feat(phone): name prompt, paste-link, quick-adds, vote toggle, SSE"
```

---

## Task 17: README + manual smoke instructions

Write the README with setup, run, deploy-to-laptop notes, and the manual smoke test from the spec.

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Office Jukebox

LAN-only office jukebox. Coworkers paste YouTube links and upvote from their
phones; one device (hooked to speakers) shows a live leaderboard and plays the
top 4 on demand.

## Quick start

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    # edit .env: set ADMIN_TOKEN to a value only you know
    # set PUBLIC_URL to whatever your coworkers will type/scan,
    # e.g. http://my-laptop.local:8000 or http://192.168.1.42:8000

    uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

## URLs

| Surface | Path | Notes |
|---|---|---|
| Phone view | `/` | What everyone scans from their phone. |
| Jukebox view | `/jukebox` | Open on the laptop hooked to speakers. |
| Jukebox view (admin) | `/jukebox?admin=<token>` | Adds Play / Reset / Skip / Stop buttons. |
| Health check | `/healthz` | |

## Finding the right URL on your network

On macOS / most modern Linux, your hostname is available as
`<hostname>.local` (mDNS). Set `PUBLIC_URL` in `.env` to e.g.
`http://my-laptop.local:8000` and that's what the QR code will encode.

If `.local` doesn't work on your network, use your machine's LAN IP
(`ipconfig getifaddr en0` on macOS).

## Manual smoke test

1. Start server. Open `/jukebox` on the laptop and confirm the QR code
   appears.
2. From a phone on the same WiFi, scan the QR. Confirm the phone view loads
   and the name prompt shows.
3. Pick a name, paste a YouTube link. Confirm the song appears on the
   jukebox screen within ~1s.
4. Tap a decade chip and pick a quick-add. Confirm it appears.
5. Add the same link again. Confirm the "already in the list — upvoted"
   message and that the heart is filled.
6. From a second phone, upvote a song. Confirm the count updates on both
   screens.
7. On the laptop, open `/jukebox?admin=<token>` and click "Play top 4".
   Confirm each video plays in sequence and auto-advances when it ends.
8. Click Skip mid-song. Confirm the next video starts.
9. Click Stop. Confirm return to idle.
10. Click "Reset for tomorrow". Confirm both screens empty out.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `ADMIN_TOKEN` | Required. Shared secret for `/api/play`, `/api/reset`, `/jukebox?admin=…`. |
| `PUBLIC_URL` | The URL the QR code encodes. Defaults to `http://localhost:8000`. |
| `PORT` | Defaults to 8000. |
| `DB_PATH` | SQLite file path. Defaults to `jukebox.db`. |

## Running tests

    pytest

## Portability

The whole app is one FastAPI process + one SQLite file. To move to a
Raspberry Pi or a small cloud box later, copy the project, install the
deps, set `.env`, and run the same `uvicorn` command. No other
infrastructure changes.
```

- [ ] **Step 2: Run all tests one more time**

```bash
pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with quick start and smoke test"
```

---

## Self-review notes

- **Spec coverage:** all sections of the spec are covered by tasks 1–17.
  Identity is implemented via headers + localStorage (spec §Identity).
  Live updates via SSE with polling fallback (spec §Realtime). Three tables
  with the correct unique indexes (spec §Data model). All endpoints from the
  API table exist with the right contracts. Duplicate→upvote behavior is
  tested. Embed-error skip + toast is in Task 15. QR code is in Task 14.
- **Placeholder check:** the only "placeholder" content is in the seed
  songs in Task 5, where a few YouTube ids are tagged as needing
  hand-curation. The schema and code don't depend on which specific videos
  are there; this is intentional and called out in the spec's "Open
  questions for the plan stage."
- **Type consistency:** `Identity`, `VideoMetadata`, `EventBroker`, song
  row shape, queue shape — names match across tasks.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-office-jukebox.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
