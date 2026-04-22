"""Raw warehouse schema, SQL helpers, and path resolution used by both adapters."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain import now_utc_iso

if TYPE_CHECKING:
    from pathlib import Path

RAW_WAREHOUSE_DIRNAME = ".ai-agents-metrics"
_RAW_WAREHOUSE_DIRNAME_LEGACY = ".codex-metrics"
RAW_WAREHOUSE_FILENAME = "warehouse.db"


def default_raw_warehouse_path(metrics_path: Path) -> Path:
    legacy_dir = metrics_path.parent / _RAW_WAREHOUSE_DIRNAME_LEGACY
    warehouse_dir = legacy_dir if legacy_dir.exists() else metrics_path.parent / RAW_WAREHOUSE_DIRNAME
    return warehouse_dir / RAW_WAREHOUSE_FILENAME


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _optional_row_value(row: sqlite3.Row | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(row, sqlite3.Row):
        # sqlite3.Row has no .get(); ``row[key]`` raises IndexError on missing
        # columns, which lets us express the default-on-miss semantics without
        # the SIM118-triggering ``key in row.keys()`` idiom.
        try:
            return row[key]
        except IndexError:
            return default
    return row.get(key, default)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_manifest (
            source_path TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            imported_at TEXT NOT NULL,
            record_count INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_threads (
            thread_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            updated_at INTEGER,
            created_at INTEGER,
            model_provider TEXT,
            model TEXT,
            cwd TEXT,
            title TEXT,
            first_user_message TEXT,
            archived INTEGER,
            rollout_path TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_sessions (
            session_path TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            thread_id TEXT,
            session_timestamp TEXT,
            cwd TEXT,
            source TEXT,
            model_provider TEXT,
            cli_version TEXT,
            originator TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_session_events (
            event_id TEXT PRIMARY KEY,
            session_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            thread_id TEXT,
            event_index INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT,
            payload_type TEXT,
            role TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_messages (
            message_id TEXT PRIMARY KEY,
            session_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            thread_id TEXT,
            event_index INTEGER NOT NULL,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_token_usage (
            token_event_id TEXT PRIMARY KEY,
            session_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            thread_id TEXT,
            event_index INTEGER NOT NULL,
            timestamp TEXT,
            has_breakdown INTEGER NOT NULL,
            input_tokens INTEGER,
            cache_creation_input_tokens INTEGER,
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
        CREATE TABLE IF NOT EXISTS raw_logs (
            source_path TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            thread_id TEXT,
            ts INTEGER,
            level TEXT,
            target TEXT,
            body TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (source_path, row_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_threads_source_path ON raw_threads(source_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_sessions_source_path ON raw_sessions(source_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_session_events_source_path ON raw_session_events(source_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_source_path ON raw_messages(source_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_token_usage_source_path ON raw_token_usage(source_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_logs_thread_id ON raw_logs(thread_id)")
    existing_raw_token_usage_columns = {row[1] for row in conn.execute("PRAGMA table_info(raw_token_usage)").fetchall()}
    if "cache_creation_input_tokens" not in existing_raw_token_usage_columns:
        conn.execute("ALTER TABLE raw_token_usage ADD COLUMN cache_creation_input_tokens INTEGER")


def _delete_source_rows(conn: sqlite3.Connection, source_path: str, source_kind: str) -> None:
    if source_kind == "thread_state_db":
        conn.execute("DELETE FROM raw_threads WHERE source_path = ?", (source_path,))
    elif source_kind in ("session_rollout", "claude_session"):
        conn.execute("DELETE FROM raw_sessions WHERE source_path = ?", (source_path,))
        conn.execute("DELETE FROM raw_session_events WHERE source_path = ?", (source_path,))
        conn.execute("DELETE FROM raw_messages WHERE source_path = ?", (source_path,))
        conn.execute("DELETE FROM raw_token_usage WHERE source_path = ?", (source_path,))
        if source_kind == "claude_session":
            conn.execute("DELETE FROM raw_threads WHERE source_path = ?", (source_path,))
    elif source_kind == "usage_log_db":
        conn.execute("DELETE FROM raw_logs WHERE source_path = ?", (source_path,))
    conn.execute("DELETE FROM source_manifest WHERE source_path = ?", (source_path,))


def _upsert_manifest(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    source_kind: str,
    content_hash: str,
    size_bytes: int,
    mtime_ns: int,
    record_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO source_manifest (
            source_path,
            source_kind,
            content_hash,
            size_bytes,
            mtime_ns,
            imported_at,
            record_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            source_kind=excluded.source_kind,
            content_hash=excluded.content_hash,
            size_bytes=excluded.size_bytes,
            mtime_ns=excluded.mtime_ns,
            imported_at=excluded.imported_at,
            record_count=excluded.record_count
        """,
        (
            str(source_path),
            source_kind,
            content_hash,
            size_bytes,
            mtime_ns,
            now_utc_iso(),
            record_count,
        ),
    )
