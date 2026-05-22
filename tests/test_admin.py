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
