"""Voting deadline: a single shared cutoff after which votes/adds are rejected.

Stored in the settings table as an ISO-8601 UTC timestamp under the
`voting_deadline` key. Absent (or unparseable) means voting is open forever.
The server clock — not the client's — is the source of truth for open/closed.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db import get_connection, transaction

_KEY = "voting_deadline"
_OFFICE_TZ = ZoneInfo("Asia/Jerusalem")
_RESET_HOUR = 11
_RESET_MINUTE = 45


def get_deadline() -> datetime | None:
    """Return the deadline as a timezone-aware UTC datetime, or None when unset."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = %s", (_KEY,)
        ).fetchone()
    if not row or not row["value"]:
        return None
    raw = row["value"].replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def set_deadline(dt: datetime | None) -> None:
    """Store the deadline (UTC), or clear it when given None."""
    with transaction() as conn:
        if dt is None:
            conn.execute("DELETE FROM settings WHERE key = %s", (_KEY,))
            return
        iso = dt.astimezone(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (_KEY, iso),
        )


def next_day_deadline() -> datetime:
    """Tomorrow at 11:45 office-local time (Asia/Jerusalem), as a UTC datetime."""
    tomorrow = (datetime.now(_OFFICE_TZ) + timedelta(days=1)).date()
    local_dt = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day,
        _RESET_HOUR, _RESET_MINUTE, tzinfo=_OFFICE_TZ,
    )
    return local_dt.astimezone(timezone.utc)


def voting_is_open() -> bool:
    """Open when there is no deadline or the deadline is still in the future."""
    deadline = get_deadline()
    if deadline is None:
        return True
    return datetime.now(timezone.utc) < deadline
