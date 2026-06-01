from datetime import datetime, timedelta, timezone

from app.voting import set_deadline


def _headers(voter_id: str = "v-1", name: str = "Maya") -> dict:
    return {"X-Voter-Id": voter_id, "X-Display-Name": name}


def _add(client, httpx_mock, vid: str = "aaaaaaaaaaa") -> str:
    httpx_mock.add_response(json={"title": "A", "thumbnail_url": "x"})
    return client.post(
        "/api/songs",
        json={"youtube_url": f"https://youtu.be/{vid}"},
        headers=_headers(),
    ).json()["id"]


def test_get_deadline_defaults_to_null(client):
    body = client.get("/api/voting-deadline").json()
    assert body["deadline"] is None
    assert body["server_now"]


def test_set_deadline_requires_admin(client):
    response = client.post("/api/voting-deadline", json={"deadline": "2026-06-02T11:45:00Z"})
    assert response.status_code in (403, 500)


def test_set_and_get_deadline(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    iso = "2026-06-02T11:45:00Z"
    response = client.post(
        "/api/voting-deadline",
        json={"deadline": iso},
        headers={"X-Admin-Token": "s3cret"},
    )
    assert response.status_code == 200
    assert response.json()["deadline"] == "2026-06-02T11:45:00+00:00"

    body = client.get("/api/voting-deadline").json()
    assert body["deadline"] == "2026-06-02T11:45:00+00:00"


def test_set_bad_deadline_is_400(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    response = client.post(
        "/api/voting-deadline",
        json={"deadline": "not-a-date"},
        headers={"X-Admin-Token": "s3cret"},
    )
    assert response.status_code == 400


def test_vote_rejected_after_deadline(client, httpx_mock):
    song_id = _add(client, httpx_mock)
    set_deadline(datetime.now(timezone.utc) - timedelta(minutes=1))
    response = client.post(f"/api/songs/{song_id}/vote", headers=_headers("v-2", "Dan"))
    assert response.status_code == 403
    assert response.json()["detail"] == "Voting has closed"


def test_add_rejected_after_deadline(client):
    # No httpx mock: the 403 fires before any oEmbed lookup happens.
    set_deadline(datetime.now(timezone.utc) - timedelta(minutes=1))
    response = client.post(
        "/api/songs",
        json={"youtube_url": "https://youtu.be/bbbbbbbbbbb"},
        headers=_headers(),
    )
    assert response.status_code == 403


def test_vote_allowed_before_deadline(client, httpx_mock):
    song_id = _add(client, httpx_mock)
    set_deadline(datetime.now(timezone.utc) + timedelta(hours=1))
    response = client.post(f"/api/songs/{song_id}/vote", headers=_headers("v-2", "Dan"))
    assert response.status_code == 200


def test_reset_clears_deadline(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    set_deadline(datetime.now(timezone.utc) - timedelta(minutes=1))
    client.post("/api/reset", headers={"X-Admin-Token": "s3cret"})
    assert client.get("/api/voting-deadline").json()["deadline"] is None
