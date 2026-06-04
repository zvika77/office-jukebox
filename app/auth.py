"""Google sign-in identity for voters.

Voters authenticate with Supabase Auth (Google provider, @nexite.io only).
Every request carrying `Authorization: Bearer <jwt>` is verified against
Supabase's published public keys (ES256, fetched from the JWKS endpoint) —
there is no shared secret to store. The domain rule is enforced server-side:
the Google `hd` hint on the frontend is only a nudge, not a guarantee.

`identity_from_claims` is a pure function (no network, no FastAPI) so the
domain logic is unit-testable without minting real tokens.
"""

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException
from functools import lru_cache

import jwt
from jwt import PyJWKClient


@dataclass(frozen=True)
class Identity:
    voter_id: str
    display_name: str


def _allowed_domain() -> str:
    return os.environ.get("ALLOWED_EMAIL_DOMAIN", "nexite.io")


def identity_from_claims(claims: dict, allowed_domain: str) -> Identity:
    """Build an Identity from decoded JWT claims, enforcing the email domain.

    Raises HTTPException(403) for a missing/foreign-domain email and
    HTTPException(401) when the subject (`sub`) is absent.
    """
    email_raw = (claims.get("email") or "").strip()
    email = email_raw.lower()
    domain = "@" + allowed_domain.lower().lstrip("@")
    if not email or not email.endswith(domain):
        raise HTTPException(status_code=403, detail="sign in with a nexite.io account")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token has no subject")

    meta = claims.get("user_metadata") or {}
    name = (meta.get("name") or meta.get("full_name") or email_raw).strip()
    return Identity(voter_id=str(sub), display_name=name[:80])


def _jwks_url() -> str:
    base = os.environ.get("SUPABASE_URL")
    if not base:
        raise RuntimeError("SUPABASE_URL is not set")
    return f"{base.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    # PyJWKClient caches fetched keys in-process, so cold starts pay one fetch.
    return PyJWKClient(_jwks_url())


def _signing_key_for(token: str):
    """Return the public key that signed `token` (test seam — monkeypatched in tests)."""
    return _jwk_client().get_signing_key_from_jwt(token).key


def _decode(token: str) -> dict:
    key = _signing_key_for(token)
    return jwt.decode(
        token,
        key,
        algorithms=["ES256"],
        audience="authenticated",
        options={"require": ["exp", "sub"]},
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_identity(authorization: str | None = Header(default=None)) -> Identity:
    """Verified @nexite.io identity for write endpoints. 401/403 when absent or foreign."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="sign in required")
    try:
        claims = _decode(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return identity_from_claims(claims, _allowed_domain())


def optional_identity(authorization: str | None = Header(default=None)) -> Identity | None:
    """Identity for public reads. None when no/invalid token — never raises, so a
    stale phone token can't break the anonymous TV read path."""
    token = _bearer_token(authorization)
    if not token:
        return None
    try:
        claims = _decode(token)
        return identity_from_claims(claims, _allowed_domain())
    except (jwt.PyJWTError, HTTPException):
        return None
