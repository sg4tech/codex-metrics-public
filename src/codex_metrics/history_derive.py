from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DeriveSummary:
    warehouse_path: Path
    projects: int
    goals: int
    attempts: int
    timeline_events: int
    retry_chains: int
    message_facts: int
    session_usage: int


def render_derive_summary_json(summary: DeriveSummary) -> str:
    payload = {
        "warehouse_path": str(summary.warehouse_path),
        "projects": summary.projects,
        "goals": summary.goals,
        "attempts": summary.attempts,
        "timeline_events": summary.timeline_events,
        "retry_chains": summary.retry_chains,
        "message_facts": summary.message_facts,
        "session_usage": summary.session_usage,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _normalize_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


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
    return cleaned if cleaned else None


def _pick_earliest_timestamp(current: str | None, candidate: str | None) -> str | None:
    current_value = _normalize_timestamp(current)
    candidate_value = _normalize_timestamp(candidate)
    if current_value is None:
        return candidate_value
    if candidate_value is None:
        return current_value
    return candidate_value if candidate_value < current_value else current_value


def _pick_latest_timestamp(current: str | None, candidate: str | None) -> str | None:
    current_value = _normalize_timestamp(current)
    candidate_value = _normalize_timestamp(candidate)
    if current_value is None:
        return candidate_value
    if candidate_value is None:
        return current_value
    return candidate_value if candidate_value > current_value else current_value


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


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_goals (
            thread_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            cwd TEXT,
            model_provider TEXT,
            model TEXT,
            title TEXT,
            archived INTEGER,
            session_count INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            log_count INTEGER NOT NULL,
            timeline_event_count INTEGER NOT NULL,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_attempts (
            attempt_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            session_timestamp TEXT,
            cwd TEXT,
            source TEXT,
            model_provider TEXT,
            cli_version TEXT,
            originator TEXT,
            event_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            first_event_at TEXT,
            last_event_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_timeline_events (
            timeline_event_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT,
            attempt_index INTEGER,
            event_type TEXT NOT NULL,
            event_rank INTEGER NOT NULL,
            event_order INTEGER NOT NULL,
            timestamp TEXT,
            summary TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_message_facts (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT NOT NULL,
            attempt_index INTEGER,
            event_index INTEGER NOT NULL,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            message_timestamp TEXT,
            message_date TEXT,
            text TEXT NOT NULL,
            model TEXT,
            usage_event_id TEXT,
            usage_event_index INTEGER,
            usage_timestamp TEXT,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            total_tokens INTEGER,
            raw_json TEXT NOT NULL
        )
        """
    )
    existing_message_fact_columns = {row[1] for row in conn.execute("PRAGMA table_info(derived_message_facts)").fetchall()}
    if "model" not in existing_message_fact_columns:
        conn.execute("ALTER TABLE derived_message_facts ADD COLUMN model TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_retry_chains (
            thread_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            attempt_count INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            has_retry_pressure INTEGER NOT NULL,
            first_attempt_session_path TEXT,
            last_attempt_session_path TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_session_usage (
            session_usage_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            total_tokens INTEGER,
            first_usage_at TEXT,
            last_usage_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_projects (
            project_cwd TEXT PRIMARY KEY,
            thread_count INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL,
            retry_thread_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            log_count INTEGER NOT NULL,
            timeline_event_count INTEGER NOT NULL,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_goals_cwd ON derived_goals(cwd)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_attempts_thread_id ON derived_attempts(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_timeline_thread_id ON derived_timeline_events(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_thread_id ON derived_message_facts(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_session_path ON derived_message_facts(session_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_message_date ON derived_message_facts(message_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_model ON derived_message_facts(model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_retry_chains_thread_id ON derived_retry_chains(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_session_usage_thread_id ON derived_session_usage(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_projects_cwd ON derived_projects(project_cwd)")


def _clear_derived_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM derived_goals")
    conn.execute("DELETE FROM derived_attempts")
    conn.execute("DELETE FROM derived_timeline_events")
    conn.execute("DELETE FROM derived_message_facts")
    conn.execute("DELETE FROM derived_retry_chains")
    conn.execute("DELETE FROM derived_session_usage")
    conn.execute("DELETE FROM derived_projects")


def _fetch_normalized_threads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT thread_id, source_path, cwd, model_provider, model, title, archived,
               session_count, event_count, message_count, log_count,
               first_seen_at, last_seen_at, raw_json
        FROM normalized_threads
        ORDER BY thread_id
        """
    ).fetchall()


def _fetch_normalized_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT session_path, thread_id, source_path, session_timestamp, cwd, source,
               model_provider, cli_version, originator, event_count, message_count,
               first_event_at, last_event_at, raw_json
        FROM normalized_sessions
        ORDER BY thread_id, session_timestamp, session_path
        """
    ).fetchall()


def _fetch_normalized_messages(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT message_id, thread_id, session_path, source_path, event_index, message_index,
               role, text, timestamp, raw_json
        FROM normalized_messages
        ORDER BY thread_id, session_path, event_index, message_index
        """
    ).fetchall()


def _fetch_normalized_usage_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT usage_event_id, thread_id, session_path, source_path, event_index, timestamp,
               input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
               total_tokens, model, raw_json
        FROM normalized_usage_events
        ORDER BY thread_id, session_path, event_index, usage_event_id
        """
    ).fetchall()


def _fetch_normalized_logs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT source_path, row_id, thread_id, ts, ts_iso, level, target, body, raw_json
        FROM normalized_logs
        ORDER BY thread_id, ts, row_id
        """
    ).fetchall()


def _sum_known_int(values: list[int | None]) -> int | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered)


def _derived_attempt_id(thread_id: str, session_path: str) -> str:
    return hashlib.sha256(f"{thread_id}:{session_path}".encode("utf-8")).hexdigest()


def _session_usage_id(session_path: str) -> str:
    return hashlib.sha256(session_path.encode("utf-8")).hexdigest()


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


def _resolve_message_model(usage_event: sqlite3.Row | None, thread_model: str | None) -> str | None:
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


def derive_codex_history(*, warehouse_path: Path) -> DeriveSummary:
    if not warehouse_path.exists():
        raise ValueError(f"Warehouse does not exist: {warehouse_path}")

    projects = 0
    goals = 0
    attempts = 0
    timeline_events = 0
    retry_chains = 0
    message_facts = 0
    session_usage = 0

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        try:
            normalized_threads = _fetch_normalized_threads(conn)
            normalized_sessions = _fetch_normalized_sessions(conn)
            normalized_messages = _fetch_normalized_messages(conn)
            normalized_usage_events = _fetch_normalized_usage_events(conn)
            normalized_logs = _fetch_normalized_logs(conn)
        except sqlite3.OperationalError as exc:
            raise ValueError(
                "Warehouse does not contain normalized Codex history; run normalize-codex-history first"
            ) from exc

        sessions_by_thread: dict[str, list[sqlite3.Row]] = {}
        messages_by_session: dict[str, list[sqlite3.Row]] = {}
        usage_events_by_session: dict[str, list[sqlite3.Row]] = {}
        logs_by_thread: dict[str, list[sqlite3.Row]] = {}
        project_stats: dict[str, dict[str, Any]] = {}

        def get_project_stats(project_cwd: str) -> dict[str, Any]:
            stats = project_stats.get(project_cwd)
            if stats is None:
                stats = {
                    "thread_count": 0,
                    "attempt_count": 0,
                    "retry_thread_count": 0,
                    "message_count": 0,
                    "usage_event_count": 0,
                    "log_count": 0,
                    "timeline_event_count": 0,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "first_seen_at": None,
                    "last_seen_at": None,
                }
                project_stats[project_cwd] = stats
            return stats

        for session_row in normalized_sessions:
            thread_id = session_row["thread_id"]
            if thread_id is None:
                continue
            sessions_by_thread.setdefault(thread_id, []).append(session_row)

        for message_row in normalized_messages:
            session_path = message_row["session_path"]
            messages_by_session.setdefault(session_path, []).append(message_row)

        for usage_row in normalized_usage_events:
            session_path = usage_row["session_path"]
            usage_events_by_session.setdefault(session_path, []).append(usage_row)

        for log_row in normalized_logs:
            thread_id = log_row["thread_id"]
            if thread_id is None:
                continue
            logs_by_thread.setdefault(thread_id, []).append(log_row)

        _clear_derived_tables(conn)

        message_usage_groups: dict[str, dict[int, list[sqlite3.Row]]] = {}
        for session_path, session_messages in messages_by_session.items():
            assistant_event_indices = sorted(
                {
                    int(message_row["event_index"])
                    for message_row in session_messages
                    if message_row["role"] == "assistant"
                }
            )
            if not assistant_event_indices:
                continue
            usage_groups_for_session: dict[int, list[sqlite3.Row]] = {}
            for usage_row in usage_events_by_session.get(session_path, []):
                usage_event_index = int(usage_row["event_index"])
                target_event_index = _resolve_assistant_message_event_index(
                    usage_event_index,
                    assistant_event_indices,
                )
                if target_event_index is None:
                    continue
                usage_groups_for_session.setdefault(target_event_index, []).append(usage_row)
            if usage_groups_for_session:
                message_usage_groups[session_path] = usage_groups_for_session

        for thread_row in normalized_threads:
            thread_id = thread_row["thread_id"]
            project_cwd = _normalize_project_cwd(thread_row["cwd"])
            if project_cwd is not None:
                stats = get_project_stats(project_cwd)
                stats["thread_count"] += 1
                stats["attempt_count"] += int(thread_row["session_count"] or 0)
                stats["retry_thread_count"] += 1 if int(thread_row["session_count"] or 0) > 1 else 0
                stats["message_count"] += int(thread_row["message_count"] or 0)
                stats["log_count"] += int(thread_row["log_count"] or 0)
                stats["first_seen_at"] = _pick_earliest_timestamp(stats["first_seen_at"], thread_row["first_seen_at"])
                stats["last_seen_at"] = _pick_latest_timestamp(stats["last_seen_at"], thread_row["last_seen_at"])
            thread_sessions = sessions_by_thread.get(thread_id, [])
            thread_messages = [row for row in normalized_messages if row["thread_id"] == thread_id]
            thread_usage_events = [row for row in normalized_usage_events if row["thread_id"] == thread_id]
            thread_logs = logs_by_thread.get(thread_id, [])
            if project_cwd is not None:
                stats = get_project_stats(project_cwd)
                stats["usage_event_count"] += len(thread_usage_events)

            timeline_items: list[dict[str, Any]] = []
            for session_index, session_row in enumerate(thread_sessions, start=1):
                timeline_items.append(
                    {
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
                    }
                )

            for message_row in thread_messages:
                attempt_index = next(
                    (index for index, session_row in enumerate(thread_sessions, start=1) if session_row["session_path"] == message_row["session_path"]),
                    None,
                )
                timeline_items.append(
                    {
                        "thread_id": thread_id,
                        "source_path": message_row["source_path"],
                        "session_path": message_row["session_path"],
                        "attempt_index": attempt_index,
                        "event_type": "message",
                        "event_rank": 1,
                        "event_order": int(message_row["event_index"]),
                        "timestamp": _normalize_timestamp(message_row["timestamp"]),
                        "summary": _compact_text(f"{message_row['role']}: {message_row['text']}"),
                        "raw_json": message_row["raw_json"],
                    }
                )

            message_rows_by_session: dict[str, list[sqlite3.Row]] = {}
            for message_row in thread_messages:
                message_rows_by_session.setdefault(message_row["session_path"], []).append(message_row)

            for session_path, session_message_rows in message_rows_by_session.items():
                usage_groups_for_session = message_usage_groups.get(session_path, {})
                session_attempt_index: int | None = next(
                    (index for index, session_row in enumerate(thread_sessions, start=1) if session_row["session_path"] == session_path),
                    None,
                )
                for message_row in session_message_rows:
                    usage_rows = usage_groups_for_session.get(int(message_row["event_index"]), [])
                    input_tokens = _sum_known_int([row["input_tokens"] for row in usage_rows])
                    cached_input_tokens = _sum_known_int([row["cached_input_tokens"] for row in usage_rows])
                    output_tokens = _sum_known_int([row["output_tokens"] for row in usage_rows])
                    reasoning_output_tokens = _sum_known_int([row["reasoning_output_tokens"] for row in usage_rows])
                    total_tokens = _sum_known_int([row["total_tokens"] for row in usage_rows])
                    usage_event = usage_rows[0] if usage_rows else None
                    usage_event_id = None if usage_event is None else usage_event["usage_event_id"]
                    message_usage_event_index: int | None = None if usage_event is None else int(usage_event["event_index"])
                    usage_timestamp = None if usage_event is None else _normalize_timestamp(usage_event["timestamp"])
                    message_model = _resolve_message_model(usage_event, thread_row["model"])
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
                            message_row["thread_id"],
                            message_row["source_path"],
                            message_row["session_path"],
                            session_attempt_index,
                            message_row["event_index"],
                            message_row["message_index"],
                            message_row["role"],
                            message_timestamp,
                            _message_date_from_timestamp(message_timestamp),
                            message_row["text"],
                            message_model,
                            usage_event_id,
                            message_usage_event_index,
                            usage_timestamp,
                            input_tokens,
                            cached_input_tokens,
                            output_tokens,
                            reasoning_output_tokens,
                            total_tokens,
                            message_row["raw_json"],
                        ),
                    )
                    message_facts += 1

            for usage_row in thread_usage_events:
                attempt_index = next(
                    (index for index, session_row in enumerate(thread_sessions, start=1) if session_row["session_path"] == usage_row["session_path"]),
                    None,
                )
                timeline_items.append(
                    {
                        "thread_id": thread_id,
                        "source_path": usage_row["source_path"],
                        "session_path": usage_row["session_path"],
                        "attempt_index": attempt_index,
                        "event_type": "usage_event",
                        "event_rank": 2,
                        "event_order": int(usage_row["event_index"]),
                        "timestamp": _normalize_timestamp(usage_row["timestamp"]),
                        "summary": _compact_text(
                            f"usage tokens={usage_row['total_tokens']} model={usage_row['model'] or ''}".strip()
                        ),
                        "raw_json": usage_row["raw_json"],
                    }
                )

            for log_row in thread_logs:
                timeline_items.append(
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
                )

            timeline_items.sort(key=_timeline_sort_key)

            if project_cwd is not None:
                stats = get_project_stats(project_cwd)
                stats["timeline_event_count"] += len(timeline_items)

            for event_order, item in enumerate(timeline_items, start=1):
                timeline_event_id = _timeline_event_id(
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
                        timeline_event_id,
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
                timeline_events += 1

            sorted_sessions = sorted(
                thread_sessions,
                key=lambda row: (
                    1 if _normalize_timestamp(row["session_timestamp"]) is None else 0,
                    _normalize_timestamp(row["session_timestamp"]) or "",
                    row["session_path"],
                ),
            )
            for attempt_index, session_row in enumerate(sorted_sessions, start=1):
                session_path = session_row["session_path"]
                attempt_id = _derived_attempt_id(thread_id, session_path)
                usage_rows = usage_events_by_session.get(session_path, [])
                usage_input_tokens = _sum_known_int([row["input_tokens"] for row in usage_rows])
                usage_cached_input_tokens = _sum_known_int([row["cached_input_tokens"] for row in usage_rows])
                usage_output_tokens = _sum_known_int([row["output_tokens"] for row in usage_rows])
                usage_reasoning_output_tokens = _sum_known_int([row["reasoning_output_tokens"] for row in usage_rows])
                usage_total_tokens = _sum_known_int([row["total_tokens"] for row in usage_rows])
                if project_cwd is not None:
                    stats = get_project_stats(project_cwd)
                    stats["input_tokens"] += usage_input_tokens or 0
                    stats["cached_input_tokens"] += usage_cached_input_tokens or 0
                    stats["output_tokens"] += usage_output_tokens or 0
                    stats["total_tokens"] += usage_total_tokens or 0
                conn.execute(
                    """
                    INSERT INTO derived_attempts (
                        attempt_id, thread_id, source_path, session_path, attempt_index,
                        session_timestamp, cwd, source, model_provider, cli_version, originator,
                        event_count, message_count, usage_event_count, first_event_at, last_event_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
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

                session_usage_id = _session_usage_id(session_path)
                conn.execute(
                    """
                    INSERT INTO derived_session_usage (
                        session_usage_id, thread_id, source_path, session_path, attempt_index,
                        usage_event_count, input_tokens, cached_input_tokens, output_tokens,
                        reasoning_output_tokens, total_tokens, first_usage_at, last_usage_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_usage_id,
                        thread_id,
                        session_row["source_path"],
                        session_path,
                        attempt_index,
                        len(usage_rows),
                        usage_input_tokens,
                        usage_cached_input_tokens,
                        usage_output_tokens,
                        usage_reasoning_output_tokens,
                        usage_total_tokens,
                        _normalize_timestamp(min((row["timestamp"] for row in usage_rows if _normalize_timestamp(row["timestamp"]) is not None), default=None)),
                        _normalize_timestamp(max((row["timestamp"] for row in usage_rows if _normalize_timestamp(row["timestamp"]) is not None), default=None)),
                        json.dumps(
                            {
                                "thread_id": thread_id,
                                "session_path": session_path,
                                "attempt_index": attempt_index,
                                "usage_event_count": len(usage_rows),
                                "input_tokens": usage_input_tokens,
                                "cached_input_tokens": usage_cached_input_tokens,
                                "output_tokens": usage_output_tokens,
                                "reasoning_output_tokens": usage_reasoning_output_tokens,
                                "total_tokens": usage_total_tokens,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
                session_usage += 1

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
                    len(sorted_sessions),
                    max(len(sorted_sessions) - 1, 0),
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
                    first_attempt_session_path, last_attempt_session_path, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    thread_row["source_path"],
                    len(sorted_sessions),
                    max(len(sorted_sessions) - 1, 0),
                    1 if len(sorted_sessions) > 1 else 0,
                    None if not sorted_sessions else sorted_sessions[0]["session_path"],
                    None if not sorted_sessions else sorted_sessions[-1]["session_path"],
                    json.dumps(
                        {
                            "thread_id": thread_id,
                            "attempt_count": len(sorted_sessions),
                            "retry_count": max(len(sorted_sessions) - 1, 0),
                            "has_retry_pressure": len(sorted_sessions) > 1,
                            "session_paths": [row["session_path"] for row in sorted_sessions],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            goals += 1
            attempts += len(sorted_sessions)
            retry_chains += 1

        for project_cwd, stats in project_stats.items():
            conn.execute(
                """
                INSERT INTO derived_projects (
                    project_cwd, thread_count, attempt_count, retry_thread_count, message_count,
                    usage_event_count, log_count, timeline_event_count, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens, first_seen_at,
                    last_seen_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_cwd,
                    stats["thread_count"],
                    stats["attempt_count"],
                    stats["retry_thread_count"],
                    stats["message_count"],
                    stats["usage_event_count"],
                    stats["log_count"],
                    stats["timeline_event_count"],
                    stats["input_tokens"] or None,
                    stats["cached_input_tokens"] or None,
                    stats["output_tokens"] or None,
                    stats["total_tokens"] or None,
                    stats["first_seen_at"],
                    stats["last_seen_at"],
                    json.dumps(
                        {
                            "project_cwd": project_cwd,
                            "thread_count": stats["thread_count"],
                            "attempt_count": stats["attempt_count"],
                            "retry_thread_count": stats["retry_thread_count"],
                            "message_count": stats["message_count"],
                            "usage_event_count": stats["usage_event_count"],
                            "log_count": stats["log_count"],
                            "timeline_event_count": stats["timeline_event_count"],
                            "input_tokens": stats["input_tokens"],
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
            projects += 1

        conn.commit()

    return DeriveSummary(
        warehouse_path=warehouse_path,
        projects=projects,
        goals=goals,
        attempts=attempts,
        timeline_events=timeline_events,
        retry_chains=retry_chains,
        message_facts=message_facts,
        session_usage=session_usage,
    )
