import pytest
from fastapi import HTTPException

from app.auth import Identity, identity_from_claims


def _claims(**over) -> dict:
    base = {
        "sub": "user-abc",
        "email": "maya@nexite.io",
        "user_metadata": {"name": "Maya"},
    }
    base.update(over)
    return base


def test_identity_from_valid_nexite_claims():
    ident = identity_from_claims(_claims(), "nexite.io")
    assert ident == Identity(voter_id="user-abc", display_name="Maya")


def test_display_name_falls_back_to_full_name():
    ident = identity_from_claims(
        _claims(user_metadata={"full_name": "Maya Doe"}), "nexite.io"
    )
    assert ident.display_name == "Maya Doe"


def test_display_name_falls_back_to_email_when_no_name():
    ident = identity_from_claims(
        _claims(email="Maya@Nexite.IO", user_metadata={}), "nexite.io"
    )
    assert ident.display_name == "Maya@Nexite.IO"


def test_foreign_domain_is_rejected_403():
    with pytest.raises(HTTPException) as exc:
        identity_from_claims(_claims(email="someone@gmail.com"), "nexite.io")
    assert exc.value.status_code == 403


def test_missing_email_is_rejected_403():
    with pytest.raises(HTTPException) as exc:
        identity_from_claims(_claims(email=None), "nexite.io")
    assert exc.value.status_code == 403


def test_missing_sub_is_rejected_401():
    with pytest.raises(HTTPException) as exc:
        identity_from_claims(_claims(sub=None), "nexite.io")
    assert exc.value.status_code == 401


def test_domain_check_is_case_insensitive():
    ident = identity_from_claims(_claims(email="Maya@Nexite.IO"), "nexite.io")
    assert ident.voter_id == "user-abc"
    assert ident.display_name == "Maya"


from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.auth as auth_module
from app.auth import optional_identity, require_identity


@pytest.fixture
def es256_keys():
    priv = ec.generate_private_key(ec.SECP256R1())
    return priv, priv.public_key()


def _mint(priv, **over) -> str:
    payload = {
        "sub": "user-abc",
        "email": "maya@nexite.io",
        "user_metadata": {"name": "Maya"},
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    payload.update(over)
    return jwt.encode(payload, priv, algorithm="ES256")


def _verify_app() -> FastAPI:
    api = FastAPI()

    @api.get("/required")
    def required(identity: Identity = Depends(require_identity)) -> dict:
        return {"voter_id": identity.voter_id, "display_name": identity.display_name}

    @api.get("/optional")
    def optional(identity: Identity | None = Depends(optional_identity)) -> dict:
        return {"signed_in": identity is not None}

    return api


def test_required_accepts_valid_nexite_token(monkeypatch, es256_keys):
    priv, pub = es256_keys
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    resp = client.get("/required", headers={"Authorization": f"Bearer {_mint(priv)}"})
    assert resp.status_code == 200
    assert resp.json() == {"voter_id": "user-abc", "display_name": "Maya"}


def test_required_rejects_foreign_domain_403(monkeypatch, es256_keys):
    priv, pub = es256_keys
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    token = _mint(priv, email="someone@gmail.com")
    resp = client.get("/required", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_required_without_token_is_401():
    client = TestClient(_verify_app())
    assert client.get("/required").status_code == 401


def test_required_with_bad_signature_is_401(monkeypatch, es256_keys):
    priv, pub = es256_keys
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    token = _mint(other)  # signed with a key the verifier won't accept
    resp = client.get("/required", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_optional_returns_signed_out_without_token():
    client = TestClient(_verify_app())
    resp = client.get("/optional")
    assert resp.status_code == 200
    assert resp.json() == {"signed_in": False}


def test_optional_swallows_bad_token(monkeypatch, es256_keys):
    priv, pub = es256_keys
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    token = _mint(other)  # invalid signature must not 500 the read path
    resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"signed_in": False}


def test_optional_personalizes_with_valid_token(monkeypatch, es256_keys):
    priv, pub = es256_keys
    monkeypatch.setattr(auth_module, "_signing_key_for", lambda token: pub)
    client = TestClient(_verify_app())
    resp = client.get("/optional", headers={"Authorization": f"Bearer {_mint(priv)}"})
    assert resp.json() == {"signed_in": True}
