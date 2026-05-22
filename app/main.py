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
