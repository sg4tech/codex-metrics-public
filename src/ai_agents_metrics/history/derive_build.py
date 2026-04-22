"""Index-building and row-fetch helpers for the derive stage."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import sqlite3

    from ai_agents_metrics.history.normalize import (
        NormalizedLogRow,
        NormalizedMessageRow,
        NormalizedSessionRow,
        NormalizedThreadRow,
        NormalizedUsageEventRow,
    )


def _normalize_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _message_date_from_timestamp(value: str | None) -> str | None:
    timestamp = _normalize_timestamp(value)
    if timestamp is None:
        return None
    if len(timestamp) < 10:
        return None
    return timestamp[:10]


def _normalize_project_cwd(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _parent_project_cwd(value: Any) -> str | None:
    """Return the parent project cwd, collapsing Claude Code worktree paths into their root.

    Worktrees created by Claude Code live under ``<project>/.claude/worktrees/<name>``.
    Any thread whose cwd matches that pattern is attributed to ``<project>`` instead,
    so worktree activity is merged into the parent project when aggregating stats.
    """
    raw = _normalize_project_cwd(value)
    if raw is None:
        return None
    marker = "/.claude/worktrees/"
    idx = raw.find(marker)
    if idx == -1:
        return raw
    parent = raw[:idx]
    return parent or raw


def _pick_earliest_timestamp(current: str | None, candidate: str | None) -> str | None:
    current_value = _normalize_timestamp(current)
    candidate_value = _normalize_timestamp(candidate)
    if current_value is None:
        return candidate_value
    if candidate_value is None:
        return current_value
    return min(current_value, candidate_value)


def _pick_latest_timestamp(current: str | None, candidate: str | None) -> str | None:
    current_value = _normalize_timestamp(current)
    candidate_value = _normalize_timestamp(candidate)
    if current_value is None:
        return candidate_value
    if candidate_value is None:
        return current_value
    return max(current_value, candidate_value)


def _compact_text(value: str | None, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}…"


def _timeline_sort_key(item: dict[str, Any]) -> tuple[int, str, int, str, str, int, str]:
    timestamp = _normalize_timestamp(item.get("timestamp"))
    return (
        1 if timestamp is None else 0,
        timestamp or "",
        int(item.get("event_rank") or 0),
        str(item.get("thread_id") or ""),
        str(item.get("session_path") or ""),
        int(item.get("event_order") or 0),
        str(item.get("event_type") or ""),
    )


def _fetch_normalized_threads(conn: sqlite3.Connection) -> list[NormalizedThreadRow]:
    rows = conn.execute(
        """
        SELECT thread_id, source_path, cwd, model_provider, model, title, archived,
               session_count, event_count, message_count, log_count,
               first_seen_at, last_seen_at, raw_json
        FROM normalized_threads
        ORDER BY thread_id
        """
    ).fetchall()
    return [cast("NormalizedThreadRow", dict(row)) for row in rows]


def _fetch_normalized_sessions(conn: sqlite3.Connection) -> list[NormalizedSessionRow]:
    rows = conn.execute(
        """
        SELECT session_path, thread_id, source_path, session_timestamp, cwd, source,
               model_provider, cli_version, originator, event_count, message_count,
               first_event_at, last_event_at, raw_json
        FROM normalized_sessions
        ORDER BY thread_id, session_timestamp, session_path
        """
    ).fetchall()
    return [cast("NormalizedSessionRow", dict(row)) for row in rows]


def _fetch_normalized_messages(conn: sqlite3.Connection) -> list[NormalizedMessageRow]:
    rows = conn.execute(
        """
        SELECT message_id, thread_id, session_path, source_path, event_index, message_index,
               role, text, timestamp, raw_json
        FROM normalized_messages
        ORDER BY thread_id, session_path, event_index, message_index
        """
    ).fetchall()
    return [cast("NormalizedMessageRow", dict(row)) for row in rows]


def _fetch_normalized_usage_events(conn: sqlite3.Connection) -> list[NormalizedUsageEventRow]:
    rows = conn.execute(
        """
        SELECT usage_event_id, thread_id, session_path, source_path, event_index, timestamp,
               input_tokens, cache_creation_input_tokens, cached_input_tokens,
               output_tokens, reasoning_output_tokens, total_tokens, model, raw_json
        FROM normalized_usage_events
        ORDER BY thread_id, session_path, event_index, usage_event_id
        """
    ).fetchall()
    return [cast("NormalizedUsageEventRow", dict(row)) for row in rows]


def _fetch_normalized_logs(conn: sqlite3.Connection) -> list[NormalizedLogRow]:
    rows = conn.execute(
        """
        SELECT source_path, row_id, thread_id, ts, ts_iso, level, target, body, raw_json
        FROM normalized_logs
        ORDER BY thread_id, ts, row_id
        """
    ).fetchall()
    return [cast("NormalizedLogRow", dict(row)) for row in rows]


def _build_index_maps(
    normalized_sessions: list[NormalizedSessionRow],
    normalized_messages: list[NormalizedMessageRow],
    normalized_usage_events: list[NormalizedUsageEventRow],
    normalized_logs: list[NormalizedLogRow],
) -> tuple[
    dict[str, list[NormalizedSessionRow]],
    dict[str, list[NormalizedMessageRow]],
    dict[str, list[NormalizedMessageRow]],
    dict[str, list[NormalizedUsageEventRow]],
    dict[str, list[NormalizedUsageEventRow]],
    dict[str, list[NormalizedLogRow]],
]:
    sessions_by_thread: dict[str, list[NormalizedSessionRow]] = {}
    messages_by_session: dict[str, list[NormalizedMessageRow]] = {}
    messages_by_thread: dict[str, list[NormalizedMessageRow]] = {}
    usage_events_by_session: dict[str, list[NormalizedUsageEventRow]] = {}
    usage_events_by_thread: dict[str, list[NormalizedUsageEventRow]] = {}
    logs_by_thread: dict[str, list[NormalizedLogRow]] = {}

    for session_row in normalized_sessions:
        if (tid := session_row["thread_id"]) is not None:
            sessions_by_thread.setdefault(tid, []).append(session_row)

    for message_row in normalized_messages:
        messages_by_session.setdefault(message_row["session_path"], []).append(message_row)
        if (tid := message_row["thread_id"]) is not None:
            messages_by_thread.setdefault(tid, []).append(message_row)

    for usage_row in normalized_usage_events:
        usage_events_by_session.setdefault(usage_row["session_path"], []).append(usage_row)
        if (tid := usage_row["thread_id"]) is not None:
            usage_events_by_thread.setdefault(tid, []).append(usage_row)

    for log_row in normalized_logs:
        if (tid := log_row["thread_id"]) is not None:
            logs_by_thread.setdefault(tid, []).append(log_row)

    return (
        sessions_by_thread,
        messages_by_session,
        messages_by_thread,
        usage_events_by_session,
        usage_events_by_thread,
        logs_by_thread,
    )


def _resolve_assistant_message_event_index(
    usage_event_index: int,
    assistant_event_indices: list[int],
) -> int | None:
    if usage_event_index in assistant_event_indices:
        return usage_event_index
    for event_index in assistant_event_indices:
        if event_index > usage_event_index:
            return event_index
    for event_index in reversed(assistant_event_indices):
        if event_index < usage_event_index:
            return event_index
    return None


def _build_message_usage_groups(
    messages_by_session: dict[str, list[NormalizedMessageRow]],
    usage_events_by_session: dict[str, list[NormalizedUsageEventRow]],
) -> dict[str, dict[int, list[NormalizedUsageEventRow]]]:
    message_usage_groups: dict[str, dict[int, list[NormalizedUsageEventRow]]] = {}
    for session_path, session_messages in messages_by_session.items():
        assistant_event_indices = sorted(
            {int(row["event_index"]) for row in session_messages if row["role"] == "assistant"}
        )
        if not assistant_event_indices:
            continue
        usage_groups: dict[int, list[NormalizedUsageEventRow]] = {}
        for usage_row in usage_events_by_session.get(session_path, []):
            target = _resolve_assistant_message_event_index(
                int(usage_row["event_index"]), assistant_event_indices
            )
            if target is not None:
                usage_groups.setdefault(target, []).append(usage_row)
        if usage_groups:
            message_usage_groups[session_path] = usage_groups
    return message_usage_groups


def _build_timeline_items(
    thread_id: str,
    thread_sessions: list[NormalizedSessionRow],
    thread_messages: list[NormalizedMessageRow],
    thread_usage_events: list[NormalizedUsageEventRow],
    thread_logs: list[NormalizedLogRow],
) -> list[dict[str, Any]]:
    session_index_map = {row["session_path"]: idx for idx, row in enumerate(thread_sessions, start=1)}
    items: list[dict[str, Any]] = []

    for session_index, session_row in enumerate(thread_sessions, start=1):
        items.append({
            "thread_id": thread_id,
            "source_path": session_row["source_path"],
            "session_path": session_row["session_path"],
            "attempt_index": session_index,
            "event_type": "session_start",
            "event_rank": 0,
            "event_order": session_index,
            "timestamp": _normalize_timestamp(session_row["session_timestamp"]),
            "summary": _compact_text(
                f"session start {session_row['session_path']} {session_row['originator'] or ''}".strip()
            ),
            "raw_json": session_row["raw_json"],
        })

    items.extend(
        {
            "thread_id": thread_id,
            "source_path": message_row["source_path"],
            "session_path": message_row["session_path"],
            "attempt_index": session_index_map.get(message_row["session_path"]),
            "event_type": "message",
            "event_rank": 1,
            "event_order": int(message_row["event_index"]),
            "timestamp": _normalize_timestamp(message_row["timestamp"]),
            "summary": _compact_text(f"{message_row['role']}: {message_row['text']}"),
            "raw_json": message_row["raw_json"],
        }
        for message_row in thread_messages
    )

    items.extend(
        {
            "thread_id": thread_id,
            "source_path": usage_row["source_path"],
            "session_path": usage_row["session_path"],
            "attempt_index": session_index_map.get(usage_row["session_path"]),
            "event_type": "usage_event",
            "event_rank": 2,
            "event_order": int(usage_row["event_index"]),
            "timestamp": _normalize_timestamp(usage_row["timestamp"]),
            "summary": _compact_text(
                f"usage tokens={usage_row['total_tokens']} model={usage_row['model'] or ''}".strip()
            ),
            "raw_json": usage_row["raw_json"],
        }
        for usage_row in thread_usage_events
    )

    items.extend(
        {
            "thread_id": thread_id,
            "source_path": log_row["source_path"],
            "session_path": None,
            "attempt_index": None,
            "event_type": "log",
            "event_rank": 3,
            "event_order": int(log_row["row_id"]),
            "timestamp": _normalize_timestamp(log_row["ts_iso"]),
            "summary": _compact_text(log_row["body"] or log_row["target"]),
            "raw_json": log_row["raw_json"],
        }
        for log_row in thread_logs
    )

    items.sort(key=_timeline_sort_key)
    return items
