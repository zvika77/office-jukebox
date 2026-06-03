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


def test_display_name_falls_back_to_email_when_no_name():
    ident = identity_from_claims(
        _claims(user_metadata={}), "nexite.io"
    )
    assert ident.display_name == "maya@nexite.io"


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
