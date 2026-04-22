"""Property-based tests for ``history.normalize.normalize_codex_history``.

Each property draws a ``WarehouseSpec`` from ``tests/strategies/history``,
materialises it into a fresh in-process SQLite warehouse, runs
``normalize_codex_history``, and asserts an invariant on the resulting
``normalized_*`` tables.

Tests deliberately avoid the ingest CLI subprocess — each hypothesis example
must complete in well under a second to keep iteration fast. The warehouse
builder writes raw_* rows directly with sqlite3.
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from strategies.history import WarehouseSpec, build_warehouse, warehouse_state

from ai_agents_metrics.history.normalize import normalize_codex_history

if TYPE_CHECKING:
    from pathlib import Path

# Each example runs multiple SQLite INSERTs + normalize queries; 10 draws keep
# the property check meaningful while staying within the 60s timeout.
# ``function_scoped_fixture`` is suppressed because tmp_path is reused per
# draw (our build_warehouse unlinks the previous file).
NORMALIZE_SETTINGS = settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)


def _dump_table(warehouse_path: Path, table: str, order_by: str) -> list[tuple[object, ...]]:
    """Return ORDER BY pk dump of a normalized table, excluding rowid."""
    with sqlite3.connect(warehouse_path) as conn:
        cursor = conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}")  # nosec B608
        return [tuple(row) for row in cursor.fetchall()]


# ── 1. Idempotency ──────────────────────────────────────────────────────────


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_normalize_is_idempotent(tmp_path: Path, spec: WarehouseSpec) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    first_run = {
        "threads": _dump_table(warehouse, "normalized_threads", "thread_id"),
        "sessions": _dump_table(warehouse, "normalized_sessions", "session_path"),
        "usage_events": _dump_table(warehouse, "normalized_usage_events", "usage_event_id"),
        "messages": _dump_table(warehouse, "normalized_messages", "message_id"),
        "projects": _dump_table(warehouse, "normalized_projects", "project_cwd"),
    }
    normalize_codex_history(warehouse_path=warehouse)
    second_run = {
        "threads": _dump_table(warehouse, "normalized_threads", "thread_id"),
        "sessions": _dump_table(warehouse, "normalized_sessions", "session_path"),
        "usage_events": _dump_table(warehouse, "normalized_usage_events", "usage_event_id"),
        "messages": _dump_table(warehouse, "normalized_messages", "message_id"),
        "projects": _dump_table(warehouse, "normalized_projects", "project_cwd"),
    }
    assert first_run == second_run


# ── 2. Primary-key uniqueness ───────────────────────────────────────────────


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_primary_keys_are_unique(tmp_path: Path, spec: WarehouseSpec) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        for table, key_expr in (
            ("normalized_threads", "thread_id"),
            ("normalized_sessions", "session_path"),
            ("normalized_messages", "message_id"),
            ("normalized_usage_events", "usage_event_id"),
            ("normalized_projects", "project_cwd"),
            ("normalized_logs", "source_path || ':' || row_id"),
        ):
            total, distinct = conn.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT {key_expr}) FROM {table}"  # nosec B608
            ).fetchone()
            assert total == distinct, f"{table} has duplicate PK ({total} rows, {distinct} distinct)"


# ── 3. FK propagation — every non-null session.thread_id exists in threads ──


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_session_thread_ids_are_known(tmp_path: Path, spec: WarehouseSpec) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        orphans = conn.execute(
            """
            SELECT s.thread_id
            FROM normalized_sessions s
            LEFT JOIN normalized_threads t ON t.thread_id = s.thread_id
            WHERE s.thread_id IS NOT NULL AND t.thread_id IS NULL
            """
        ).fetchall()
    assert orphans == [], f"sessions reference unknown thread_ids: {orphans}"


# ── 4. Timestamp ordering — first_event_at ≤ last_event_at per row ──────────


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_timestamps_are_monotonic(tmp_path: Path, spec: WarehouseSpec) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        for table, (first, last) in (
            ("normalized_sessions", ("first_event_at", "last_event_at")),
            ("normalized_threads", ("first_seen_at", "last_seen_at")),
        ):
            rows = conn.execute(
                f"SELECT {first}, {last} FROM {table}"  # nosec B608
            ).fetchall()
            for first_at, last_at in rows:
                if first_at is not None and last_at is not None:
                    assert first_at <= last_at, f"{table}: {first_at} > {last_at}"


# ── 5. Null symmetry — if all input timestamps null, normalized fields null ─


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state(max_threads=3, max_sessions_per_thread=2))
def test_null_input_timestamps_yield_null_normalized(
    tmp_path: Path, spec: WarehouseSpec
) -> None:
    # Force every session_event to carry a null timestamp; all other rows stay
    # as drawn. The invariant we check: for each session whose every input
    # event timestamp is null/blank, normalized_sessions.first_event_at and
    # last_event_at are both NULL.
    for event in spec.session_events:
        event["timestamp"] = None
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        rows = conn.execute(
            "SELECT session_path, first_event_at, last_event_at FROM normalized_sessions"
        ).fetchall()
    # Usage-event timestamps can still populate first/last_event_at, so we
    # scope the assertion to sessions that have no usage-event timestamps either.
    usage_timestamped_session_paths = {
        entry["session_path"]
        for entry in spec.token_usage
        if entry.get("timestamp") not in (None, "")
    }
    for session_path, first_at, last_at in rows:
        if session_path in usage_timestamped_session_paths:
            continue
        assert first_at is None, f"expected NULL first_event_at for {session_path}, got {first_at!r}"
        assert last_at is None, f"expected NULL last_event_at for {session_path}, got {last_at!r}"


# ── 6. Counter bounds — session.message_count equals actual messages ────────


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_session_message_count_matches_messages(tmp_path: Path, spec: WarehouseSpec) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        counter_rows = conn.execute(
            "SELECT session_path, message_count FROM normalized_sessions"
        ).fetchall()
        actual_rows = dict(
            conn.execute(
                "SELECT session_path, COUNT(*) FROM normalized_messages GROUP BY session_path"
            ).fetchall()
        )
    for session_path, counter in counter_rows:
        actual = actual_rows.get(session_path, 0)
        assert counter == actual, f"{session_path}: message_count={counter} vs actual={actual}"


# ── 7. Raw JSON preservation for messages ───────────────────────────────────


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_raw_message_json_preserved_through_normalize(
    tmp_path: Path, spec: WarehouseSpec
) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        normalized = dict(
            conn.execute("SELECT message_id, raw_json FROM normalized_messages").fetchall()
        )
    raw_by_id = {row["message_id"]: row["raw_json"] for row in spec.messages}
    for message_id, normalized_raw in normalized.items():
        assert normalized_raw == raw_by_id[message_id]


# ── 8. Row count bound — normalized never exceeds raw ───────────────────────


@pytest.mark.timeout(60)
@NORMALIZE_SETTINGS
@given(warehouse_state())
def test_normalized_row_counts_bounded_by_raw(tmp_path: Path, spec: WarehouseSpec) -> None:
    warehouse = build_warehouse(tmp_path, spec)
    normalize_codex_history(warehouse_path=warehouse)
    with sqlite3.connect(warehouse) as conn:
        def _count(table: str) -> int:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608
            count: int = cursor.fetchone()[0]
            return count

        assert _count("normalized_threads") <= _count("raw_threads")
        assert _count("normalized_sessions") <= _count("raw_sessions")
        assert _count("normalized_messages") <= _count("raw_messages")
        # Usage events come from two raw sources (raw_session_events with
        # event_type='token_count' AND raw_token_usage). The upper bound is
        # the sum of both, minus any deduplication (same event_index).
        usage_upper = _count("raw_session_events") + _count("raw_token_usage")
        assert _count("normalized_usage_events") <= usage_upper
