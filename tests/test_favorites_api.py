from app.db import get_connection


def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def _add_song(client, httpx_mock, vid: str, title: str = "Song") -> str:
    httpx_mock.add_response(
        json={"title": title, "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}
    )
    return client.post(
        "/api/songs",
        json={"youtube_url": f"https://youtu.be/{vid}"},
        headers=_headers(),
    ).json()["id"]


def test_favorites_returns_seeded_rows(client):
    response = client.get("/api/favorites")
    assert response.status_code == 200
    data = response.json()
    # The curated starter set, all at love_score 0 until real votes accumulate.
    assert len(data) == 12
    assert {"youtube_id", "title", "thumbnail_url", "love_score"} <= data[0].keys()
    assert all(row["love_score"] == 0 for row in data)


def test_favorites_public_read_without_sign_in(client):
    # No X-Voter-Id header — the Hall of Fame is a public read, like quick-adds.
    response = client.get("/api/favorites")
    assert response.status_code == 200


def test_reset_accumulates_votes_into_love_score(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    vid = "loveme00001"
    sid = _add_song(client, httpx_mock, vid, title="Crowd Pleaser")  # adder = 1 vote
    for voter in ("v-2", "v-3"):
        client.post(f"/api/songs/{sid}/vote", headers=_headers(voter, voter))
    # 3 votes total: the adder plus two upvotes.

    client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})

    data = client.get("/api/favorites").json()
    top = data[0]  # highest love_score sorts first, ahead of the 0-score seeds
    assert top["youtube_id"] == vid
    assert top["love_score"] == 3
    assert top["title"] == "Crowd Pleaser"


def test_love_score_accumulates_across_multiple_resets(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    vid = "repeat00001"

    # Day 1: added (1 adder vote) + one upvote = 2 votes.
    sid = _add_song(client, httpx_mock, vid)
    client.post(f"/api/songs/{sid}/vote", headers=_headers("v-2", "v-2"))
    client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})

    # Day 2: the song is re-added fresh (1 adder vote) after the wipe.
    _add_song(client, httpx_mock, vid)
    client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})

    fav = next(r for r in client.get("/api/favorites").json() if r["youtube_id"] == vid)
    assert fav["love_score"] == 3  # 2 from day 1 + 1 from day 2


def test_times_added_increments_each_reset(client, httpx_mock, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    vid = "counted0001"
    _add_song(client, httpx_mock, vid)
    client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})
    _add_song(client, httpx_mock, vid)
    client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})

    with get_connection() as conn:
        row = conn.execute(
            "SELECT times_added FROM favorites WHERE youtube_id = %s", (vid,)
        ).fetchone()
    assert row["times_added"] == 2
