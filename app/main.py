import io
import os
import socket
import uuid
from datetime import datetime, timezone

import qrcode
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sse_starlette.sse import EventSourceResponse

from app.admin import require_admin
from app.db import get_connection, transaction
from app.events import broker, publish_sync
from app.identity import Identity, require_identity
from app.seed_data import QUICK_ADDS, thumbnail_for
from app.youtube import (
    YouTubeAPIError,
    extract_playlist_id,
    extract_video_id,
    fetch_playlist_songs,
    fetch_video_metadata,
    search_songs_for_decade,
)

app = FastAPI(title="Office Jukebox")


def _detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _public_url() -> str:
    url = os.environ.get("PUBLIC_URL", "").strip()
    if url and url != "http://localhost:8000":
        return url
    port = os.environ.get("PORT", "8000")
    return f"http://{_detect_lan_ip()}:{port}"


def seed_quick_adds() -> None:
    """Seed from hardcoded list only when the table is empty."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM quick_adds").fetchone()[0]
    if count > 0:
        return
    with transaction() as c:
        for entry in QUICK_ADDS:
            c.execute(
                "INSERT INTO quick_adds (youtube_id, title, thumbnail_url, decade) "
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
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if api_key:
        try:
            _do_refresh(api_key)
        except Exception as exc:
            # Log but don't crash — the container should still come up
            import sys
            print(f"[startup] quick-add refresh failed (will retry on next /refresh): {exc}", file=sys.stderr)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AddSongBody(BaseModel):
    youtube_url: str


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


_DECADES = ["60s", "70s", "80s", "90s", "2000s", "2010s"]


def _do_refresh(api_key: str) -> list[dict]:
    playlist_raw = os.environ.get("YOUTUBE_PLAYLIST_ID", "").strip()

    if playlist_raw:
        # ── Playlist mode ──────────────────────────────────────────────────────
        pid = extract_playlist_id(playlist_raw)
        if not pid:
            raise HTTPException(
                status_code=400,
                detail="YOUTUBE_PLAYLIST_ID is not a valid playlist ID or URL",
            )
        try:
            songs = fetch_playlist_songs(pid, api_key)
        except YouTubeAPIError as exc:
            raise HTTPException(status_code=502, detail=f"YouTube API error: {exc}")
        if not songs:
            raise HTTPException(
                status_code=502,
                detail="Playlist returned no videos — make sure it's public and the ID is correct",
            )
        with transaction() as conn:
            conn.execute("DELETE FROM quick_adds")
            for s in songs:
                conn.execute(
                    "INSERT INTO quick_adds (youtube_id, title, thumbnail_url, decade) VALUES (?, ?, ?, ?)",
                    (s["youtube_id"], s["title"], s["thumbnail_url"], None),
                )
    else:
        # ── Fallback: decade-based search ──────────────────────────────────────
        all_songs: list[dict] = []
        for decade in _DECADES:
            try:
                decade_songs = search_songs_for_decade(decade, api_key)
            except YouTubeAPIError as exc:
                raise HTTPException(status_code=502, detail=f"YouTube API error: {exc}")
            all_songs.extend(decade_songs)

        if not all_songs:
            raise HTTPException(
                status_code=502,
                detail="YouTube search returned no results — check your API key",
            )

        seen: set[str] = set()
        unique_songs = []
        for s in all_songs:
            if s["youtube_id"] not in seen:
                seen.add(s["youtube_id"])
                unique_songs.append(s)

        with transaction() as conn:
            conn.execute("DELETE FROM quick_adds")
            for s in unique_songs:
                conn.execute(
                    "INSERT INTO quick_adds (youtube_id, title, thumbnail_url, decade) VALUES (?, ?, ?, ?)",
                    (s["youtube_id"], s["title"], s["thumbnail_url"], s.get("decade")),
                )

    rows = get_connection().execute(
        "SELECT youtube_id, title, thumbnail_url, decade FROM quick_adds ORDER BY rowid"
    ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/quick-adds/refresh")
def refresh_quick_adds() -> list[dict]:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="YOUTUBE_API_KEY not set in server config")
    return _do_refresh(api_key)


@app.post("/api/songs", status_code=201)
def add_song(
    body: AddSongBody,
    identity: Identity = Depends(require_identity),
):
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
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (song_id, video_id, meta.title, meta.thumbnail_url, None, identity.display_name, _now()),
        )

    publish_sync("songs_changed")
    return {
        "id": song_id,
        "youtube_id": video_id,
        "title": meta.title,
        "thumbnail_url": meta.thumbnail_url,
        "added_by_name": identity.display_name,
        "already_in_list": False,
    }


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
    publish_sync("songs_changed")
    return {"id": song_id, "did_i_vote": did_i_vote, "votes": votes}


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


@app.post("/api/reset")
def reset_day(_: None = Depends(require_admin)) -> dict[str, int]:
    with transaction() as tx:
        votes_cur = tx.execute("DELETE FROM votes")
        songs_cur = tx.execute("DELETE FROM songs")
    publish_sync("songs_changed")
    return {
        "deleted_songs": songs_cur.rowcount,
        "deleted_votes": votes_cur.rowcount,
    }


@app.get("/api/events")
async def events():
    async def stream():
        async with broker.subscribe() as queue:
            yield {"event": "hello", "data": "connected"}
            while True:
                message = await queue.get()
                yield {"event": message, "data": message}

    return EventSourceResponse(stream())


@app.get("/api/qrcode.png")
def qrcode_png() -> Response:
    public_url = _public_url()
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
