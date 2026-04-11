"""Date and time-bucket helpers for the HTML report pipeline.

All functions are pure (no I/O, no side effects) and work with naive or
aware :class:`datetime` objects.  Timezone info is stripped before any
arithmetic so that warehouse timestamps and ndjson timestamps (which may
carry different offsets) are compared on equal footing.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _parse_date(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a :class:`datetime`.

    Returns ``None`` for ``None`` input or unparseable strings.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _monday_of(dt: datetime) -> datetime:
    """Return the Monday of the ISO week containing *dt* (time zeroed, tz-naive)."""
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )


def _make_buckets(earliest: datetime, latest: datetime, gran: str) -> list[str]:
    """Return an ordered list of bucket keys spanning *earliest* → *latest*.

    *gran* must be ``"day"`` or ``"week"``.  Daily buckets are ``YYYY-MM-DD``
    strings; weekly buckets are the Monday of each ISO week.
    """
    keys: list[str] = []
    if gran == "day":
        cur = earliest.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        end = latest.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        while cur <= end:
            keys.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
    else:
        cur = _monday_of(earliest.replace(tzinfo=None))
        end = _monday_of(latest.replace(tzinfo=None))
        while cur <= end:
            keys.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(weeks=1)
    return keys


def _bucket_key(dt: datetime, gran: str) -> str:
    """Map *dt* to the bucket key it belongs to under *gran*."""
    naive = dt.replace(tzinfo=None)
    if gran == "day":
        return naive.strftime("%Y-%m-%d")
    return _monday_of(naive).strftime("%Y-%m-%d")
