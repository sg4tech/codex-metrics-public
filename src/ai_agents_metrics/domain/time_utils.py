"""ISO-8601 parsing and UTC-aware ``now_*`` helpers for the domain layer."""
from __future__ import annotations

from datetime import UTC, datetime


def now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def now_utc_datetime() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def parse_iso_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc

    if parsed.tzinfo is None:
        raise ValueError(f"Invalid {field_name}: timezone offset is required")
    return parsed


def parse_iso_datetime_flexible(value: str, field_name: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return parse_iso_datetime(normalized, field_name)


def choose_earliest_timestamp(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if parse_iso_datetime(first, "timestamp") <= parse_iso_datetime(second, "timestamp") else second


def choose_latest_timestamp(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if parse_iso_datetime(first, "timestamp") >= parse_iso_datetime(second, "timestamp") else second
