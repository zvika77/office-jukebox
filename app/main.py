import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_connection, transaction
from app.identity import Identity, require_identity
from app.seed_data import QUICK_ADDS, thumbnail_for
from app.youtube import extract_video_id, fetch_video_metadata

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
    return {"id": song_id, "did_i_vote": did_i_vote, "votes": votes}
