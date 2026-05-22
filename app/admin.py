import os

from fastapi import Header, HTTPException, Query


def require_admin(
    x_admin_token: str | None = Header(default=None),
    admin: str | None = Query(default=None),
) -> None:
    configured = os.environ.get("ADMIN_TOKEN")
    if not configured:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    provided = x_admin_token or admin
    if provided != configured:
        raise HTTPException(status_code=403, detail="admin token required")
