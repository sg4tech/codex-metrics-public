"""Hypothesis strategies for raw_* warehouse rows used by normalize tests.

The strategy produces a ``WarehouseSpec`` — a plain data bundle of rows for
each ``raw_*`` table — that can be fed into ``build_warehouse(tmp_path, spec)``
to populate an in-process SQLite warehouse. The schema is the one created by
``ai_agents_metrics.history.ingest._ensure_schema``.

FK consistency is maintained by draw order: threads → sessions (referencing a
drawn ``thread_id``) → events / token usage / messages (referencing a drawn
``session_path``). Primary keys are always unique because they are seeded
with the draw index.

The warehouse builder uses direct ``INSERT`` statements (no subprocess, no
ingest CLI) — mandatory for hypothesis throughput under the test timeout.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hypothesis import strategies as st

from ai_agents_metrics.history.ingest import _ensure_schema

if TYPE_CHECKING:
    from pathlib import Path

# Column order for each raw_* table. Read lazily on first use so any schema
# drift in ingest._ensure_schema triggers a test failure instead of a silent
# misalignment. The module-level cache keeps subsequent draws cheap.
_column_cache: dict[str, tuple[str, ...]] = {}


def _raw_table_columns(table: str) -> tuple[str, ...]:
    if table in _column_cache:
        return _column_cache[table]
    conn = sqlite3.connect(":memory:")
    try:
        _ensure_schema(conn)
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # nosec B608
    finally:
        conn.close()
    columns = tuple(row[1] for row in rows)
    _column_cache[table] = columns
    return columns


@dataclass
class WarehouseSpec:
    """Materialised draw: one entry per raw_* table."""

    threads: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    session_events: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    token_usage: list[dict[str, Any]] = field(default_factory=list)


_TIMESTAMPS = st.sampled_from(
    [
        None,
        "",
        "2025-06-01T00:00:00Z",
        "2025-06-01T10:15:30+00:00",
        "2025-06-02T18:45:12Z",
        "2025-06-03T09:00:00+00:00",
    ]
)


def _raw_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


@st.composite
def warehouse_state(
    draw: st.DrawFn,
    *,
    max_threads: int = 3,
    max_sessions_per_thread: int = 2,
    max_events_per_session: int = 4,
    max_token_rows_per_session: int = 2,
    max_messages_per_session: int = 3,
) -> WarehouseSpec:
    """Draw a warehouse spec with consistent FK references and unique PKs."""
    spec = WarehouseSpec()
    thread_count = draw(st.integers(min_value=0, max_value=max_threads))
    for thread_index in range(thread_count):
        thread_id = f"t-{thread_index:04d}"
        source_path = f"/src/threads/{thread_id}.sqlite"
        spec.threads.append(
            {
                "thread_id": thread_id,
                "source_path": source_path,
                "updated_at": draw(st.one_of(st.none(), st.integers(min_value=0, max_value=2**30))),
                "created_at": draw(st.one_of(st.none(), st.integers(min_value=0, max_value=2**30))),
                "model_provider": draw(st.sampled_from([None, "openai", "anthropic"])),
                "model": draw(st.sampled_from([None, "gpt-4", "sonnet-4", "haiku-4"])),
                "cwd": draw(st.sampled_from([None, "/repo/alpha", "/repo/beta"])),
                "title": draw(st.sampled_from([None, "alpha run", "beta run"])),
                "first_user_message": draw(st.sampled_from([None, "hello"])),
                "archived": draw(st.sampled_from([0, 1])),
                "rollout_path": f"/rollouts/{thread_id}.jsonl",
                "raw_json": _raw_json({"thread_id": thread_id, "marker": thread_index}),
            }
        )
        session_count = draw(st.integers(min_value=0, max_value=max_sessions_per_thread))
        for session_index in range(session_count):
            session_path = f"/src/sessions/{thread_id}-{session_index:03d}.jsonl"
            session_source = f"/src/sessions/{thread_id}-{session_index:03d}.jsonl"
            spec.sessions.append(
                {
                    "session_path": session_path,
                    "source_path": session_source,
                    "thread_id": thread_id,
                    "session_timestamp": draw(_TIMESTAMPS),
                    "cwd": draw(st.sampled_from([None, "/repo/alpha", "/repo/beta"])),
                    "source": draw(st.sampled_from(["codex", "claude", None])),
                    "model_provider": draw(st.sampled_from([None, "openai", "anthropic"])),
                    "cli_version": draw(st.sampled_from([None, "0.1.0", "1.0.0"])),
                    "originator": draw(st.sampled_from([None, "cli", "ide"])),
                    "raw_json": _raw_json(
                        {"session_path": session_path, "index": session_index}
                    ),
                }
            )
            _draw_events_and_messages(
                draw,
                spec,
                thread_id=thread_id,
                session_path=session_path,
                session_source=session_source,
                max_events_per_session=max_events_per_session,
                max_messages_per_session=max_messages_per_session,
            )
            _draw_token_usage(
                draw,
                spec,
                thread_id=thread_id,
                session_path=session_path,
                session_source=session_source,
                max_token_rows_per_session=max_token_rows_per_session,
            )
    return spec


def _draw_events_and_messages(
    draw: st.DrawFn,
    spec: WarehouseSpec,
    *,
    thread_id: str,
    session_path: str,
    session_source: str,
    max_events_per_session: int,
    max_messages_per_session: int,
) -> None:
    event_count = draw(st.integers(min_value=0, max_value=max_events_per_session))
    for event_index in range(event_count):
        event_id = f"{session_path}-evt-{event_index:03d}"
        spec.session_events.append(
            {
                "event_id": event_id,
                "session_path": session_path,
                "source_path": session_source,
                "thread_id": thread_id,
                "event_index": event_index,
                "event_type": draw(st.sampled_from(["message", "token_count", "tool_use"])),
                "timestamp": draw(_TIMESTAMPS),
                "payload_type": draw(st.sampled_from([None, "text", "json"])),
                "role": draw(st.sampled_from([None, "user", "assistant", "system"])),
                "raw_json": _raw_json({"event_id": event_id, "index": event_index}),
            }
        )
    message_count = draw(st.integers(min_value=0, max_value=max_messages_per_session))
    for message_index in range(message_count):
        message_id = f"{session_path}-msg-{message_index:03d}"
        spec.messages.append(
            {
                "message_id": message_id,
                "session_path": session_path,
                "source_path": session_source,
                "thread_id": thread_id,
                "event_index": message_index,
                "message_index": message_index,
                "role": draw(st.sampled_from(["user", "assistant", "system"])),
                "text": draw(st.text(max_size=40)),
                "raw_json": _raw_json({"message_id": message_id}),
            }
        )


def _draw_token_usage(
    draw: st.DrawFn,
    spec: WarehouseSpec,
    *,
    thread_id: str,
    session_path: str,
    session_source: str,
    max_token_rows_per_session: int,
) -> None:
    token_count = draw(st.integers(min_value=0, max_value=max_token_rows_per_session))
    for token_index in range(token_count):
        token_event_id = f"{session_path}-tok-{token_index:03d}"
        input_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)))
        cached_input_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)))
        output_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)))
        # total_tokens respects the breakdown sum bound when all three parts are present.
        if input_tokens is not None and cached_input_tokens is not None and output_tokens is not None:
            low = input_tokens + cached_input_tokens + output_tokens
            total_tokens = draw(
                st.one_of(st.none(), st.integers(min_value=low, max_value=low + 5_000))
            )
        else:
            total_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=30_000)))
        spec.token_usage.append(
            {
                "token_event_id": token_event_id,
                "session_path": session_path,
                "source_path": session_source,
                "thread_id": thread_id,
                "event_index": token_index,
                "timestamp": draw(_TIMESTAMPS),
                "has_breakdown": 1,
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": draw(
                    st.one_of(st.none(), st.integers(min_value=0, max_value=5_000))
                ),
                "cached_input_tokens": cached_input_tokens,
                "output_tokens": output_tokens,
                "reasoning_output_tokens": draw(
                    st.one_of(st.none(), st.integers(min_value=0, max_value=5_000))
                ),
                "total_tokens": total_tokens,
                "model": draw(st.sampled_from([None, "gpt-4", "sonnet-4"])),
                "raw_json": _raw_json({"token_event_id": token_event_id}),
            }
        )


def _insert_rows(
    conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    columns = _raw_table_columns(table)
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"  # nosec B608
    conn.executemany(sql, [tuple(row[col] for col in columns) for row in rows])


def build_warehouse(tmp_path: Path, spec: WarehouseSpec) -> Path:
    """Write ``spec`` to a fresh SQLite warehouse and return the path."""
    warehouse_path = tmp_path / "warehouse.sqlite"
    # Remove the stale warehouse file if a previous hypothesis example ran
    # against the same tmp_path fixture — `_ensure_schema` alone is not
    # enough because primary-key inserts would collide.
    if warehouse_path.exists():
        warehouse_path.unlink()
    with sqlite3.connect(warehouse_path) as conn:
        _ensure_schema(conn)
        _insert_rows(conn, "raw_threads", spec.threads)
        _insert_rows(conn, "raw_sessions", spec.sessions)
        _insert_rows(conn, "raw_session_events", spec.session_events)
        _insert_rows(conn, "raw_messages", spec.messages)
        _insert_rows(conn, "raw_token_usage", spec.token_usage)
        conn.commit()
    return warehouse_path
