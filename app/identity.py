from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Identity:
    voter_id: str
    display_name: str


def require_identity(
    x_voter_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
) -> Identity:
    if not x_voter_id or not x_voter_id.strip():
        raise HTTPException(status_code=400, detail="X-Voter-Id header is required")
    name = (x_display_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="X-Display-Name header is required")
    if len(name) > 40:
        raise HTTPException(status_code=400, detail="display name too long (max 40 chars)")
    return Identity(voter_id=x_voter_id.strip(), display_name=name)
