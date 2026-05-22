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
    assert response.status_code == 200
    response = client.get(
        "/who",
        headers={"X-Voter-Id": "v-123", "X-Display-Name": "a" * 41},
    )
    assert response.status_code == 400
