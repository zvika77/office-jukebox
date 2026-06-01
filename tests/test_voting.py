from datetime import datetime, timedelta, timezone

from app.voting import get_deadline, set_deadline, voting_is_open


def test_voting_open_when_no_deadline(db):
    assert get_deadline() is None
    assert voting_is_open() is True


def test_voting_open_when_deadline_in_future(db):
    set_deadline(datetime.now(timezone.utc) + timedelta(hours=1))
    assert voting_is_open() is True


def test_voting_closed_when_deadline_in_past(db):
    set_deadline(datetime.now(timezone.utc) - timedelta(minutes=1))
    assert voting_is_open() is False


def test_set_deadline_roundtrips_as_utc(db):
    # A naive/local-ish input is normalised to UTC on the way out.
    target = datetime(2026, 6, 2, 11, 45, tzinfo=timezone.utc)
    set_deadline(target)
    stored = get_deadline()
    assert stored == target
    assert stored.tzinfo is not None


def test_set_deadline_none_clears_and_reopens(db):
    set_deadline(datetime.now(timezone.utc) - timedelta(minutes=1))
    assert voting_is_open() is False
    set_deadline(None)
    assert get_deadline() is None
    assert voting_is_open() is True


def test_set_new_future_deadline_reopens_after_close(db):
    set_deadline(datetime.now(timezone.utc) - timedelta(minutes=1))
    assert voting_is_open() is False
    set_deadline(datetime.now(timezone.utc) + timedelta(hours=2))
    assert voting_is_open() is True
