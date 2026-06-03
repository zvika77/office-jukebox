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
