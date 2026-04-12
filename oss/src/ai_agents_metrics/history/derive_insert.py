from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from ai_agents_metrics.history.derive_build import (
    _message_date_from_timestamp,
    _normalize_timestamp,
)
from ai_agents_metrics.history.normalize import (
    NormalizedMessageRow,
    NormalizedSessionRow,
    NormalizedThreadRow,
    NormalizedUsageEventRow,
)


def _sum_known_int(values: list[int | None]) -> int | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered)


def _derived_attempt_id(thread_id: str, session_path: str) -> str:
    return hashlib.sha256(f"{thread_id}:{session_path}".encode("utf-8")).hexdigest()


def _session_usage_id(session_path: str) -> str:
    return hashlib.sha256(session_path.encode("utf-8")).hexdigest()


def _resolve_message_model(usage_event: NormalizedUsageEventRow | None, thread_model: str | None) -> str | None:
    if usage_event is not None:
        usage_model = usage_event["model"]
        if isinstance(usage_model, str):
            cleaned = usage_model.strip()
            if cleaned:
                return cleaned
    if isinstance(thread_model, str):
        cleaned = thread_model.strip()
        if cleaned:
            return cleaned
    return None


def _timeline_event_id(thread_id: str, event_type: str, event_order: int, session_path: str | None, timestamp: str | None) -> str:
    seed = f"{thread_id}:{event_type}:{event_order}:{session_path or ''}:{timestamp or ''}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _insert_timeline_events(
    conn: sqlite3.Connection,
    thread_id: str,
    timeline_items: list[dict[str, Any]],
) -> int:
    count = 0
    for event_order, item in enumerate(timeline_items, start=1):
        event_id = _timeline_event_id(
            thread_id,
            str(item["event_type"]),
            event_order,
            item.get("session_path"),
            item.get("timestamp"),
        )
        conn.execute(
            """
            INSERT INTO derived_timeline_events (
                timeline_event_id, thread_id, source_path, session_path, attempt_index,
                event_type, event_rank, event_order, timestamp, summary, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                thread_id,
                item["source_path"],
                item.get("session_path"),
                item.get("attempt_index"),
                item["event_type"],
                item["event_rank"],
                event_order,
                item.get("timestamp"),
                item.get("summary"),
                item["raw_json"],
            ),
        )
        count += 1
    return count


def _insert_message_facts(
    conn: sqlite3.Connection,
    thread_id: str,
    thread_row: NormalizedThreadRow,
    thread_messages: list[NormalizedMessageRow],
    thread_sessions: list[NormalizedSessionRow],
    message_usage_groups: dict[str, dict[int, list[NormalizedUsageEventRow]]],
) -> int:
    session_index_map = {row["session_path"]: idx for idx, row in enumerate(thread_sessions, start=1)}
    messages_by_session: dict[str, list[NormalizedMessageRow]] = {}
    for row in thread_messages:
        messages_by_session.setdefault(row["session_path"], []).append(row)

    count = 0
    for session_path, session_messages in messages_by_session.items():
        usage_groups = message_usage_groups.get(session_path, {})
        attempt_index = session_index_map.get(session_path)
        for message_row in session_messages:
            usage_rows = usage_groups.get(int(message_row["event_index"]), [])
            usage_event = usage_rows[0] if usage_rows else None
            message_timestamp = _normalize_timestamp(message_row["timestamp"])
            conn.execute(
                """
                INSERT INTO derived_message_facts (
                    message_id, thread_id, source_path, session_path, attempt_index,
                    event_index, message_index, role, message_timestamp, message_date,
                    text, model, usage_event_id, usage_event_index, usage_timestamp,
                    input_tokens, cached_input_tokens, output_tokens,
                    reasoning_output_tokens, total_tokens, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_row["message_id"],
                    thread_id,
                    message_row["source_path"],
                    session_path,
                    attempt_index,
                    message_row["event_index"],
                    message_row["message_index"],
                    message_row["role"],
                    message_timestamp,
                    _message_date_from_timestamp(message_timestamp),
                    message_row["text"],
                    _resolve_message_model(usage_event, thread_row["model"]),
                    None if usage_event is None else usage_event["usage_event_id"],
                    None if usage_event is None else int(usage_event["event_index"]),
                    None if usage_event is None else _normalize_timestamp(usage_event["timestamp"]),
                    _sum_known_int([row["input_tokens"] for row in usage_rows]),
                    _sum_known_int([row["cached_input_tokens"] for row in usage_rows]),
                    _sum_known_int([row["output_tokens"] for row in usage_rows]),
                    _sum_known_int([row["reasoning_output_tokens"] for row in usage_rows]),
                    _sum_known_int([row["total_tokens"] for row in usage_rows]),
                    message_row["raw_json"],
                ),
            )
            count += 1
    return count


def _insert_attempts_and_session_usage(
    conn: sqlite3.Connection,
    thread_id: str,
    sorted_sessions: list[NormalizedSessionRow],
    usage_events_by_session: dict[str, list[NormalizedUsageEventRow]],
    stats_entry: dict[str, Any] | None,
) -> int:
    count = 0
    for attempt_index, session_row in enumerate(sorted_sessions, start=1):
        session_path = session_row["session_path"]
        usage_rows = usage_events_by_session.get(session_path, [])
        usage_input = _sum_known_int([r["input_tokens"] for r in usage_rows])
        usage_cache_create = _sum_known_int([r["cache_creation_input_tokens"] for r in usage_rows])
        usage_cached = _sum_known_int([r["cached_input_tokens"] for r in usage_rows])
        usage_output = _sum_known_int([r["output_tokens"] for r in usage_rows])
        usage_reasoning = _sum_known_int([r["reasoning_output_tokens"] for r in usage_rows])
        usage_total = _sum_known_int([r["total_tokens"] for r in usage_rows])

        if stats_entry is not None:
            stats_entry["input_tokens"] += usage_input or 0
            stats_entry["cache_creation_input_tokens"] += usage_cache_create or 0
            stats_entry["cached_input_tokens"] += usage_cached or 0
            stats_entry["output_tokens"] += usage_output or 0
            stats_entry["total_tokens"] += usage_total or 0

        conn.execute(
            """
            INSERT INTO derived_attempts (
                attempt_id, thread_id, source_path, session_path, attempt_index,
                session_timestamp, cwd, source, model_provider, cli_version, originator,
                event_count, message_count, usage_event_count, first_event_at, last_event_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _derived_attempt_id(thread_id, session_path),
                thread_id,
                session_row["source_path"],
                session_path,
                attempt_index,
                _normalize_timestamp(session_row["session_timestamp"]),
                session_row["cwd"],
                session_row["source"],
                session_row["model_provider"],
                session_row["cli_version"],
                session_row["originator"],
                session_row["event_count"],
                session_row["message_count"],
                len(usage_rows),
                _normalize_timestamp(session_row["first_event_at"]),
                _normalize_timestamp(session_row["last_event_at"]),
                session_row["raw_json"],
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_session_usage (
                session_usage_id, thread_id, source_path, session_path, attempt_index,
                usage_event_count, input_tokens, cache_creation_input_tokens,
                cached_input_tokens, output_tokens, reasoning_output_tokens,
                total_tokens, first_usage_at, last_usage_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _session_usage_id(session_path),
                thread_id,
                session_row["source_path"],
                session_path,
                attempt_index,
                len(usage_rows),
                usage_input,
                usage_cache_create,
                usage_cached,
                usage_output,
                usage_reasoning,
                usage_total,
                min((ts for r in usage_rows if (ts := _normalize_timestamp(r["timestamp"])) is not None), default=None),
                max((ts for r in usage_rows if (ts := _normalize_timestamp(r["timestamp"])) is not None), default=None),
                json.dumps(
                    {
                        "thread_id": thread_id,
                        "session_path": session_path,
                        "attempt_index": attempt_index,
                        "usage_event_count": len(usage_rows),
                        "input_tokens": usage_input,
                        "cache_creation_input_tokens": usage_cache_create,
                        "cached_input_tokens": usage_cached,
                        "output_tokens": usage_output,
                        "reasoning_output_tokens": usage_reasoning,
                        "total_tokens": usage_total,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        count += 1
    return count


def _insert_goal_and_retry_chain(
    conn: sqlite3.Connection,
    thread_id: str,
    thread_row: NormalizedThreadRow,
    sorted_sessions: list[NormalizedSessionRow],
    thread_usage_events: list[NormalizedUsageEventRow],
    timeline_items: list[dict[str, Any]],
) -> None:
    attempt_count = max(len(sorted_sessions), 1)
    retry_count = max(attempt_count - 1, 0)
    conn.execute(
        """
        INSERT INTO derived_goals (
            thread_id, source_path, cwd, model_provider, model, title, archived,
            session_count, attempt_count, retry_count, message_count,
            usage_event_count, log_count, timeline_event_count, first_seen_at,
            last_seen_at, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            thread_row["source_path"],
            thread_row["cwd"],
            thread_row["model_provider"],
            thread_row["model"],
            thread_row["title"],
            thread_row["archived"],
            thread_row["session_count"],
            attempt_count,
            retry_count,
            thread_row["message_count"],
            len(thread_usage_events),
            thread_row["log_count"],
            len(timeline_items),
            _normalize_timestamp(thread_row["first_seen_at"]),
            _normalize_timestamp(thread_row["last_seen_at"]),
            thread_row["raw_json"],
        ),
    )
    conn.execute(
        """
        INSERT INTO derived_retry_chains (
            thread_id, source_path, attempt_count, retry_count, has_retry_pressure,
            first_session_path, last_session_path, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            thread_row["source_path"],
            attempt_count,
            retry_count,
            1 if attempt_count > 1 else 0,
            None if not sorted_sessions else sorted_sessions[0]["session_path"],
            None if not sorted_sessions else sorted_sessions[-1]["session_path"],
            json.dumps(
                {
                    "thread_id": thread_id,
                    "attempt_count": attempt_count,
                    "retry_count": retry_count,
                    "has_retry_pressure": attempt_count > 1,
                    "session_paths": [row["session_path"] for row in sorted_sessions],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def _insert_projects(conn: sqlite3.Connection, project_stats: dict[str, dict[str, Any]]) -> int:
    count = 0
    for project_cwd, stats in project_stats.items():
        # project_cwd is already the collapsed parent path (worktree suffix stripped by
        # _parent_project_cwd at aggregation time), so parent_project_cwd == project_cwd for
        # every row.  The column exists so that read_history_signals and history_compare_store
        # can query by parent_project_cwd without needing a LIKE workaround on derived_projects.
        conn.execute(
            """
            INSERT INTO derived_projects (
                project_cwd, parent_project_cwd, thread_count, attempt_count, retry_thread_count,
                message_count, usage_event_count, log_count, timeline_event_count, input_tokens,
                cache_creation_input_tokens, cached_input_tokens, output_tokens,
                total_tokens, first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_cwd,
                project_cwd,
                stats["thread_count"],
                stats["attempt_count"],
                stats["retry_thread_count"],
                stats["message_count"],
                stats["usage_event_count"],
                stats["log_count"],
                stats["timeline_event_count"],
                stats["input_tokens"] or None,
                stats["cache_creation_input_tokens"] or None,
                stats["cached_input_tokens"] or None,
                stats["output_tokens"] or None,
                stats["total_tokens"] or None,
                stats["first_seen_at"],
                stats["last_seen_at"],
                json.dumps(
                    {
                        "project_cwd": project_cwd,
                        "parent_project_cwd": project_cwd,
                        "thread_count": stats["thread_count"],
                        "attempt_count": stats["attempt_count"],
                        "retry_thread_count": stats["retry_thread_count"],
                        "message_count": stats["message_count"],
                        "usage_event_count": stats["usage_event_count"],
                        "log_count": stats["log_count"],
                        "timeline_event_count": stats["timeline_event_count"],
                        "input_tokens": stats["input_tokens"],
                        "cache_creation_input_tokens": stats["cache_creation_input_tokens"],
                        "cached_input_tokens": stats["cached_input_tokens"],
                        "output_tokens": stats["output_tokens"],
                        "total_tokens": stats["total_tokens"],
                        "first_seen_at": stats["first_seen_at"],
                        "last_seen_at": stats["last_seen_at"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        count += 1
    return count
