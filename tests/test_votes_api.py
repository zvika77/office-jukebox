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
