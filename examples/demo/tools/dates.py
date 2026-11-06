"""Date helpers."""
from datetime import date, datetime, timezone


def parse_iso_date(text):
    """Turn '2026-11-05' into a date object."""
    return date.fromisoformat(text)


def utc_now():
    """The current time in UTC, with the time zone attached."""
    return datetime.now(timezone.utc)
