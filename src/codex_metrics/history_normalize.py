from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NormalizeSummary:
    warehouse_path: Path
    projects: int
    threads: int
    sessions: int
    messages: int
    usage_events: int
    logs: int


def render_normalize_summary_json(summary: NormalizeSummary) -> str:
    payload = {
        "warehouse_path": str(summary.warehouse_path),
        "projects": summary.projects,
        "threads": summary.threads,
        "sessions": summary.sessions,
        "messages": summary.messages,
        "usage_events": summary.usage_events,
        "logs": summary.logs,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _iso_from_unix_seconds(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat()


def _normalize_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


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


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_threads (
            thread_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            cwd TEXT,
            model_provider TEXT,
            model TEXT,
            title TEXT,
            archived INTEGER,
            created_at INTEGER,
            updated_at INTEGER,
            rollout_path TEXT,
            session_count INTEGER NOT NULL,
            event_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            log_count INTEGER NOT NULL,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_sessions (
            session_path TEXT PRIMARY KEY,
            thread_id TEXT,
            source_path TEXT NOT NULL,
            session_timestamp TEXT,
            cwd TEXT,
            source TEXT,
            model_provider TEXT,
            cli_version TEXT,
            originator TEXT,
            event_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            first_event_at TEXT,
            last_event_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_messages (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT,
            session_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            event_index INTEGER NOT NULL,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            timestamp TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_usage_events (
            usage_event_id TEXT PRIMARY KEY,
            thread_id TEXT,
            session_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            event_index INTEGER NOT NULL,
            timestamp TEXT,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            total_tokens INTEGER,
            model TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_logs (
            source_path TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            thread_id TEXT,
            ts INTEGER,
            ts_iso TEXT,
            level TEXT,
            target TEXT,
            body TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (source_path, row_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS normalized_projects (
            project_cwd TEXT PRIMARY KEY,
            thread_count INTEGER NOT NULL,
            session_count INTEGER NOT NULL,
            event_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            log_count INTEGER NOT NULL,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_threads_cwd ON normalized_threads(cwd)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_sessions_thread_id ON normalized_sessions(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_messages_thread_id ON normalized_messages(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_usage_thread_id ON normalized_usage_events(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_logs_thread_id ON normalized_logs(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_projects_cwd ON normalized_projects(project_cwd)")


def _clear_normalized_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM normalized_threads")
    conn.execute("DELETE FROM normalized_sessions")
    conn.execute("DELETE FROM normalized_messages")
    conn.execute("DELETE FROM normalized_usage_events")
    conn.execute("DELETE FROM normalized_logs")
    conn.execute("DELETE FROM normalized_projects")


def _fetch_raw_threads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT thread_id, source_path, updated_at, created_at, model_provider, model, cwd,
               title, archived, rollout_path, raw_json
        FROM raw_threads
        ORDER BY thread_id
        """
    ).fetchall()


def _fetch_raw_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT session_path, thread_id, source_path, session_timestamp, cwd, source,
               model_provider, cli_version, originator, raw_json
        FROM raw_sessions
        ORDER BY session_path
        """
    ).fetchall()


def _fetch_raw_messages(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT message_id, thread_id, session_path, source_path, event_index,
               message_index, role, text, raw_json
        FROM raw_messages
        ORDER BY thread_id, session_path, event_index, message_index
        """
    ).fetchall()


def _fetch_raw_session_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT event_id, session_path, source_path, thread_id, event_index,
               event_type, timestamp, payload_type, role, raw_json
        FROM raw_session_events
        ORDER BY thread_id, session_path, event_index
        """
    ).fetchall()


def _fetch_raw_token_usage(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT token_event_id, session_path, source_path, thread_id, event_index,
               timestamp, has_breakdown, input_tokens, cached_input_tokens,
               output_tokens, reasoning_output_tokens, total_tokens, model, raw_json
        FROM raw_token_usage
        ORDER BY thread_id, session_path, event_index
        """
    ).fetchall()


def _fetch_raw_logs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT source_path, row_id, thread_id, ts, level, target, body, raw_json
        FROM raw_logs
        ORDER BY thread_id, ts, row_id
        """
    ).fetchall()


def _usage_event_from_row(row: sqlite3.Row) -> dict[str, Any] | None:
    payload = json.loads(row["raw_json"])
    if payload.get("type") != "event_msg":
        return None
    payload_body = payload.get("payload")
    if not isinstance(payload_body, dict) or payload_body.get("type") != "token_count":
        return None
    info = payload_body.get("info")
    if not isinstance(info, dict):
        return None
    last_token_usage = info.get("last_token_usage")
    if not isinstance(last_token_usage, dict):
        return None
    event_payload = {
        "event_id": row["event_id"],
        "thread_id": row["thread_id"],
        "session_path": row["session_path"],
        "source_path": row["source_path"],
        "event_index": row["event_index"],
        "timestamp": _normalize_timestamp(payload.get("timestamp")),
        "input_tokens": last_token_usage.get("input_tokens"),
        "cached_input_tokens": last_token_usage.get("cached_input_tokens"),
        "output_tokens": last_token_usage.get("output_tokens"),
        "reasoning_output_tokens": last_token_usage.get("reasoning_output_tokens"),
        "total_tokens": last_token_usage.get("total_tokens"),
        "model": payload_body.get("info", {}).get("model"),
        "raw_json": row["raw_json"],
    }
    return event_payload


def _usage_event_from_token_row(row: sqlite3.Row) -> dict[str, Any] | None:
    if int(row["has_breakdown"] or 0) != 1:
        return None
    return {
        "event_id": row["token_event_id"],
        "thread_id": row["thread_id"],
        "session_path": row["session_path"],
        "source_path": row["source_path"],
        "event_index": row["event_index"],
        "timestamp": _normalize_timestamp(row["timestamp"]),
        "input_tokens": row["input_tokens"],
        "cached_input_tokens": row["cached_input_tokens"],
        "output_tokens": row["output_tokens"],
        "reasoning_output_tokens": row["reasoning_output_tokens"],
        "total_tokens": row["total_tokens"],
        "model": row["model"],
        "raw_json": row["raw_json"],
    }


def normalize_codex_history(*, warehouse_path: Path) -> NormalizeSummary:
    if not warehouse_path.exists():
        raise ValueError(f"Warehouse does not exist: {warehouse_path}")

    threads = 0
    projects = 0
    sessions = 0
    messages = 0
    usage_events = 0
    logs = 0

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        try:
            raw_threads = _fetch_raw_threads(conn)
            raw_sessions = _fetch_raw_sessions(conn)
            raw_messages = _fetch_raw_messages(conn)
            raw_session_events = _fetch_raw_session_events(conn)
            try:
                raw_token_usage = _fetch_raw_token_usage(conn)
            except sqlite3.OperationalError:
                raw_token_usage = []
            raw_logs = _fetch_raw_logs(conn)
        except sqlite3.OperationalError as exc:
            raise ValueError(
                "Warehouse does not contain raw Codex history; run ingest-codex-history first"
            ) from exc

        session_count_by_thread: dict[str, int] = {}
        event_count_by_thread: dict[str, int] = {}
        message_count_by_thread: dict[str, int] = {}
        log_count_by_thread: dict[str, int] = {}
        first_seen_by_thread: dict[str, str | None] = {}
        last_seen_by_thread: dict[str, str | None] = {}
        message_count_by_session: dict[str, int] = {}
        event_count_by_session: dict[str, int] = {}
        first_event_by_session: dict[str, str | None] = {}
        last_event_by_session: dict[str, str | None] = {}
        event_timestamp_by_session_index: dict[tuple[str, int], str | None] = {}
        token_usage_rows = raw_token_usage
        token_usage_by_session_index = {
            (row["session_path"], int(row["event_index"])): row
            for row in token_usage_rows
            if int(row["has_breakdown"] or 0) == 1
        }
        project_stats: dict[str, dict[str, Any]] = {}
        thread_project_cwd: dict[str, str] = {}
        threads_with_rows: set[str] = set()

        def get_project_stats(project_cwd: str) -> dict[str, Any]:
            stats = project_stats.get(project_cwd)
            if stats is None:
                stats = {
                    "thread_count": 0,
                    "session_count": 0,
                    "event_count": 0,
                    "message_count": 0,
                    "usage_event_count": 0,
                    "log_count": 0,
                    "first_seen_at": None,
                    "last_seen_at": None,
                }
                project_stats[project_cwd] = stats
            return stats

        for session_row in raw_sessions:
            thread_id = session_row["thread_id"]
            if thread_id is None:
                continue
            session_count_by_thread[thread_id] = session_count_by_thread.get(thread_id, 0) + 1
            session_timestamp = session_row["session_timestamp"]
            first_seen_by_thread[thread_id] = _pick_earliest_timestamp(first_seen_by_thread.get(thread_id), session_timestamp)
            last_seen_by_thread[thread_id] = _pick_latest_timestamp(last_seen_by_thread.get(thread_id), session_timestamp)
        for event_row in raw_session_events:
            thread_id = event_row["thread_id"]
            if thread_id is not None:
                event_count_by_thread[thread_id] = event_count_by_thread.get(thread_id, 0) + 1
                timestamp = event_row["timestamp"]
                first_seen_by_thread[thread_id] = _pick_earliest_timestamp(first_seen_by_thread.get(thread_id), timestamp)
                last_seen_by_thread[thread_id] = _pick_latest_timestamp(last_seen_by_thread.get(thread_id), timestamp)
            event_count_by_session[event_row["session_path"]] = event_count_by_session.get(event_row["session_path"], 0) + 1
            event_timestamp_by_session_index[(event_row["session_path"], int(event_row["event_index"]))] = _normalize_timestamp(
                event_row["timestamp"]
            )

        for message_row in raw_messages:
            thread_id = message_row["thread_id"]
            if thread_id is not None:
                message_count_by_thread[thread_id] = message_count_by_thread.get(thread_id, 0) + 1
            message_count_by_session[message_row["session_path"]] = message_count_by_session.get(message_row["session_path"], 0) + 1

        for log_row in raw_logs:
            thread_id = log_row["thread_id"]
            if thread_id is not None:
                log_count_by_thread[thread_id] = log_count_by_thread.get(thread_id, 0) + 1

        _clear_normalized_tables(conn)

        for thread_row in raw_threads:
            thread_id = thread_row["thread_id"]
            threads_with_rows.add(thread_id)
            project_cwd = _normalize_project_cwd(thread_row["cwd"])
            if project_cwd is not None:
                thread_project_cwd[thread_id] = project_cwd
                stats = get_project_stats(project_cwd)
                stats["thread_count"] += 1
                stats["session_count"] += session_count_by_thread.get(thread_id, 0)
                stats["event_count"] += event_count_by_thread.get(thread_id, 0)
                stats["message_count"] += message_count_by_thread.get(thread_id, 0)
                stats["first_seen_at"] = _pick_earliest_timestamp(stats["first_seen_at"], first_seen_by_thread.get(thread_id))
                stats["last_seen_at"] = _pick_latest_timestamp(stats["last_seen_at"], last_seen_by_thread.get(thread_id))
            conn.execute(
                """
                INSERT INTO normalized_threads (
                    thread_id, source_path, cwd, model_provider, model, title, archived,
                    created_at, updated_at, rollout_path, session_count, event_count,
                    message_count, log_count, first_seen_at, last_seen_at, raw_json
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
                    thread_row["created_at"],
                    thread_row["updated_at"],
                    thread_row["rollout_path"],
                    session_count_by_thread.get(thread_id, 0),
                    event_count_by_thread.get(thread_id, 0),
                    message_count_by_thread.get(thread_id, 0),
                    log_count_by_thread.get(thread_id, 0),
                    first_seen_by_thread.get(thread_id),
                    last_seen_by_thread.get(thread_id),
                    thread_row["raw_json"],
                ),
            )
            threads += 1

        for event_row in raw_session_events:
            session_path = event_row["session_path"]
            event_index = int(event_row["event_index"])
            timestamp = event_row["timestamp"]
            first_event_by_session[session_path] = _pick_earliest_timestamp(first_event_by_session.get(session_path), timestamp)
            last_event_by_session[session_path] = _pick_latest_timestamp(last_event_by_session.get(session_path), timestamp)
            token_row = token_usage_by_session_index.get((event_row["session_path"], event_index))
            usage_event = _usage_event_from_token_row(token_row) if token_row is not None else None
            if usage_event is None:
                usage_event = _usage_event_from_row(event_row)
            if usage_event is None:
                continue
            project_cwd = thread_project_cwd.get(event_row["thread_id"])
            if project_cwd is not None:
                stats = get_project_stats(project_cwd)
                stats["usage_event_count"] += 1
            usage_event_id = hashlib.sha256(
                f"{event_row['event_id']}:{event_row['session_path']}:{event_index}".encode("utf-8")
            ).hexdigest()
            conn.execute(
                """
                INSERT INTO normalized_usage_events (
                    usage_event_id, thread_id, session_path, source_path, event_index, timestamp,
                    input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens,
                    total_tokens, model, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_event_id,
                    usage_event["thread_id"],
                    usage_event["session_path"],
                    usage_event["source_path"],
                    usage_event["event_index"],
                    usage_event["timestamp"],
                    usage_event["input_tokens"],
                    usage_event["cached_input_tokens"],
                    usage_event["output_tokens"],
                    usage_event["reasoning_output_tokens"],
                    usage_event["total_tokens"],
                    usage_event["model"],
                    usage_event["raw_json"],
                ),
            )
            usage_events += 1

        for session_row in raw_sessions:
            session_path = session_row["session_path"]
            thread_id = session_row["thread_id"]
            project_cwd = _normalize_project_cwd(session_row["cwd"])
            if project_cwd is not None and thread_id is not None and thread_id not in threads_with_rows:
                thread_project_cwd[thread_id] = project_cwd
                stats = get_project_stats(project_cwd)
                stats["session_count"] += 1
                stats["event_count"] += event_count_by_session.get(session_path, 0)
                stats["message_count"] += message_count_by_session.get(session_path, 0)
                stats["first_seen_at"] = _pick_earliest_timestamp(stats["first_seen_at"], first_event_by_session.get(session_path))
                stats["last_seen_at"] = _pick_latest_timestamp(stats["last_seen_at"], last_event_by_session.get(session_path))
            conn.execute(
                """
                INSERT INTO normalized_sessions (
                    session_path, thread_id, source_path, session_timestamp, cwd, source,
                    model_provider, cli_version, originator, event_count, message_count,
                    first_event_at, last_event_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_path,
                    session_row["thread_id"],
                    session_row["source_path"],
                    session_row["session_timestamp"],
                    session_row["cwd"],
                    session_row["source"],
                    session_row["model_provider"],
                    session_row["cli_version"],
                    session_row["originator"],
                    event_count_by_session.get(session_path, 0),
                    message_count_by_session.get(session_path, 0),
                    first_event_by_session.get(session_path),
                    last_event_by_session.get(session_path),
                    session_row["raw_json"],
                ),
            )
            sessions += 1

        for message_row in raw_messages:
            timestamp = event_timestamp_by_session_index.get((message_row["session_path"], int(message_row["event_index"])))
            conn.execute(
                """
                INSERT INTO normalized_messages (
                    message_id, thread_id, session_path, source_path, event_index,
                    message_index, role, text, timestamp, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_row["message_id"],
                    message_row["thread_id"],
                    message_row["session_path"],
                    message_row["source_path"],
                    message_row["event_index"],
                    message_row["message_index"],
                    message_row["role"],
                    message_row["text"],
                    timestamp,
                    message_row["raw_json"],
                ),
            )
            messages += 1

        for log_row in raw_logs:
            project_cwd = thread_project_cwd.get(log_row["thread_id"])
            if project_cwd is not None:
                stats = get_project_stats(project_cwd)
                stats["log_count"] += 1
            conn.execute(
                """
                INSERT INTO normalized_logs (
                    source_path, row_id, thread_id, ts, ts_iso, level, target, body, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_row["source_path"],
                    log_row["row_id"],
                    log_row["thread_id"],
                    log_row["ts"],
                    _iso_from_unix_seconds(log_row["ts"]),
                    log_row["level"],
                    log_row["target"],
                    log_row["body"],
                    log_row["raw_json"],
                ),
            )
            logs += 1

        for project_cwd, stats in project_stats.items():
            conn.execute(
                """
                INSERT INTO normalized_projects (
                    project_cwd, thread_count, session_count, event_count, message_count,
                    usage_event_count, log_count, first_seen_at, last_seen_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_cwd,
                    stats["thread_count"],
                    stats["session_count"],
                    stats["event_count"],
                    stats["message_count"],
                    stats["usage_event_count"],
                    stats["log_count"],
                    stats["first_seen_at"],
                    stats["last_seen_at"],
                    json.dumps(
                        {
                            "project_cwd": project_cwd,
                            "thread_count": stats["thread_count"],
                            "session_count": stats["session_count"],
                            "event_count": stats["event_count"],
                            "message_count": stats["message_count"],
                            "usage_event_count": stats["usage_event_count"],
                            "log_count": stats["log_count"],
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

    return NormalizeSummary(
        warehouse_path=warehouse_path,
        projects=projects,
        threads=threads,
        sessions=sessions,
        messages=messages,
        usage_events=usage_events,
        logs=logs,
    )
