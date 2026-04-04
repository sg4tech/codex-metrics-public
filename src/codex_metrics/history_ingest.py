from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_metrics.domain import now_utc_iso
from codex_metrics.storage import ensure_parent_dir

RAW_WAREHOUSE_DIRNAME = ".codex-metrics"
RAW_WAREHOUSE_FILENAME = "codex_raw_history.sqlite"


@dataclass(frozen=True)
class IngestSummary:
    source_root: Path
    warehouse_path: Path
    scanned_files: int
    imported_files: int
    skipped_files: int
    projects: int
    threads: int
    sessions: int
    session_events: int
    token_count_events: int
    token_usage_events: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    messages: int
    logs: int


def default_raw_warehouse_path(metrics_path: Path) -> Path:
    return metrics_path.parent / RAW_WAREHOUSE_DIRNAME / RAW_WAREHOUSE_FILENAME


def render_ingest_summary_json(summary: IngestSummary) -> str:
    payload = {
        "source_root": str(summary.source_root),
        "warehouse_path": str(summary.warehouse_path),
        "scanned_files": summary.scanned_files,
        "imported_files": summary.imported_files,
        "skipped_files": summary.skipped_files,
        "projects": summary.projects,
        "threads": summary.threads,
        "sessions": summary.sessions,
        "session_events": summary.session_events,
        "token_count_events": summary.token_count_events,
        "token_usage_events": summary.token_usage_events,
        "input_tokens": summary.input_tokens,
        "cached_input_tokens": summary.cached_input_tokens,
        "output_tokens": summary.output_tokens,
        "reasoning_output_tokens": summary.reasoning_output_tokens,
        "total_tokens": summary.total_tokens,
        "messages": summary.messages,
        "logs": summary.logs,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


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
        return row[key] if key in row.keys() else default
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


def _delete_source_rows(conn: sqlite3.Connection, source_path: str, source_kind: str) -> None:
    if source_kind == "thread_state_db":
        conn.execute("DELETE FROM raw_threads WHERE source_path = ?", (source_path,))
    elif source_kind == "session_rollout":
        conn.execute("DELETE FROM raw_sessions WHERE source_path = ?", (source_path,))
        conn.execute("DELETE FROM raw_session_events WHERE source_path = ?", (source_path,))
        conn.execute("DELETE FROM raw_messages WHERE source_path = ?", (source_path,))
        conn.execute("DELETE FROM raw_token_usage WHERE source_path = ?", (source_path,))
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


def _import_state_db(conn: sqlite3.Connection, source_path: Path) -> int:
    imported = 0
    if not source_path.exists():
        raise ValueError(f"Source file does not exist: {source_path}")
    with sqlite3.connect(source_path) as source_conn:
        source_conn.row_factory = sqlite3.Row
        try:
            rows = source_conn.execute("SELECT * FROM threads").fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Source file is not a valid Codex thread state database: {source_path}") from exc
        conn.execute("DELETE FROM raw_threads WHERE source_path = ?", (str(source_path),))
        for row in rows:
            row_json = dict(row)
            thread_id = str(_optional_row_value(row, "id", ""))
            conn.execute(
                """
                INSERT INTO raw_threads (
                    thread_id,
                    source_path,
                    updated_at,
                    created_at,
                    model_provider,
                    model,
                    cwd,
                    title,
                    first_user_message,
                    archived,
                    rollout_path,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    str(source_path),
                    _optional_row_value(row, "updated_at"),
                    _optional_row_value(row, "created_at"),
                    _optional_row_value(row, "model_provider"),
                    _optional_row_value(row, "model"),
                    _optional_row_value(row, "cwd"),
                    _optional_row_value(row, "title"),
                    _optional_row_value(row, "first_user_message"),
                    _optional_row_value(row, "archived"),
                    _optional_row_value(row, "rollout_path"),
                    _json_text(row_json),
                ),
            )
            imported += 1
    return imported


def _extract_message_text(content: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in {"input_text", "output_text", "text"}:
                text = item.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
    elif isinstance(content, str) and content:
        texts.append(content)
    return texts


def _extract_token_usage(record: dict[str, Any], *, event_id: str, source_path: str, thread_id: str | None, event_index: int) -> dict[str, Any] | None:
    if record.get("type") != "event_msg":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None

    info = payload.get("info")
    if not isinstance(info, dict):
        info = {}
    last_token_usage = info.get("last_token_usage")
    if isinstance(last_token_usage, dict):
        has_breakdown = 1
    else:
        has_breakdown = 0
        last_token_usage = {}

    timestamp = record.get("timestamp") if isinstance(record.get("timestamp"), str) else None
    return {
        "token_event_id": event_id,
        "session_path": source_path,
        "source_path": source_path,
        "thread_id": thread_id,
        "event_index": event_index,
        "timestamp": timestamp,
        "has_breakdown": has_breakdown,
        "input_tokens": last_token_usage.get("input_tokens"),
        "cached_input_tokens": last_token_usage.get("cached_input_tokens"),
        "output_tokens": last_token_usage.get("output_tokens"),
        "reasoning_output_tokens": last_token_usage.get("reasoning_output_tokens"),
        "total_tokens": last_token_usage.get("total_tokens"),
        "model": info.get("model"),
        "raw_json": _json_text(record),
    }


def _import_session_file(conn: sqlite3.Connection, source_path: Path) -> int:
    conn.execute("DELETE FROM raw_sessions WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_session_events WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_messages WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_token_usage WHERE source_path = ?", (str(source_path),))
    imported = 0
    thread_id: str | None = None
    with source_path.open("r", encoding="utf-8") as handle:
        for event_index, line in enumerate(handle):
            if not line.strip():
                continue
            record = json.loads(line)
            record_type = str(record.get("type") or "")
            payload = record.get("payload")
            timestamp = record.get("timestamp") if isinstance(record.get("timestamp"), str) else None
            payload_type = payload.get("type") if isinstance(payload, dict) else None
            role = payload.get("role") if isinstance(payload, dict) else None
            if record_type == "session_meta" and isinstance(payload, dict):
                thread_id = str(payload.get("id") or thread_id or source_path.stem)
                conn.execute(
                    """
                    INSERT INTO raw_sessions (
                        session_path,
                        source_path,
                        thread_id,
                        session_timestamp,
                        cwd,
                        source,
                        model_provider,
                        cli_version,
                        originator,
                        raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(source_path),
                        str(source_path),
                        thread_id,
                        payload.get("timestamp"),
                        payload.get("cwd"),
                        payload.get("source"),
                        payload.get("model_provider"),
                        payload.get("cli_version"),
                        payload.get("originator"),
                        _json_text(payload),
                    ),
                )
            event_id = hashlib.sha256(f"{source_path}:{event_index}:{line}".encode("utf-8")).hexdigest()
            conn.execute(
                """
                INSERT INTO raw_session_events (
                    event_id,
                    session_path,
                    source_path,
                    thread_id,
                    event_index,
                    event_type,
                    timestamp,
                    payload_type,
                    role,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    str(source_path),
                    str(source_path),
                    thread_id,
                    event_index,
                    record_type,
                    timestamp,
                    payload_type if isinstance(payload_type, str) else None,
                    role if isinstance(role, str) else None,
                    _json_text(record),
                ),
            )
            imported += 1
            token_usage = _extract_token_usage(
                record,
                event_id=event_id,
                source_path=str(source_path),
                thread_id=thread_id,
                event_index=event_index,
            )
            if token_usage is not None:
                conn.execute(
                    """
                    INSERT INTO raw_token_usage (
                        token_event_id,
                        session_path,
                        source_path,
                        thread_id,
                        event_index,
                        timestamp,
                        has_breakdown,
                        input_tokens,
                        cached_input_tokens,
                        output_tokens,
                        reasoning_output_tokens,
                        total_tokens,
                        model,
                        raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token_usage["token_event_id"],
                        token_usage["session_path"],
                        token_usage["source_path"],
                        token_usage["thread_id"],
                        token_usage["event_index"],
                        token_usage["timestamp"],
                        token_usage["has_breakdown"],
                        token_usage["input_tokens"],
                        token_usage["cached_input_tokens"],
                        token_usage["output_tokens"],
                        token_usage["reasoning_output_tokens"],
                        token_usage["total_tokens"],
                        token_usage["model"],
                        token_usage["raw_json"],
                    ),
                )
            if record_type == "response_item" and isinstance(payload, dict):
                content = payload.get("content")
                texts = _extract_message_text(content)
                if isinstance(role, str):
                    for message_index, text in enumerate(texts):
                        message_id = hashlib.sha256(
                            f"{source_path}:{event_index}:{message_index}:{role}:{text}".encode("utf-8")
                        ).hexdigest()
                        conn.execute(
                            """
                            INSERT INTO raw_messages (
                                message_id,
                                session_path,
                                source_path,
                                thread_id,
                                event_index,
                                message_index,
                                role,
                                text,
                                raw_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                message_id,
                                str(source_path),
                                str(source_path),
                                thread_id,
                                event_index,
                                message_index,
                                role,
                                text,
                                _json_text(payload),
                            ),
                        )
    return imported


def _import_logs_db(conn: sqlite3.Connection, source_path: Path) -> int:
    imported = 0
    if not source_path.exists():
        raise ValueError(f"Source file does not exist: {source_path}")
    with sqlite3.connect(source_path) as source_conn:
        source_conn.row_factory = sqlite3.Row
        try:
            rows = source_conn.execute("SELECT rowid as source_row_id, * FROM logs").fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Source file is not a valid Codex logs database: {source_path}") from exc
        conn.execute("DELETE FROM raw_logs WHERE source_path = ?", (str(source_path),))
        for row in rows:
            row_json = dict(row)
            conn.execute(
                """
                INSERT INTO raw_logs (
                    source_path,
                    row_id,
                    thread_id,
                    ts,
                    level,
                    target,
                    body,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_path),
                    _optional_row_value(row, "source_row_id"),
                    _optional_row_value(row, "thread_id"),
                    _optional_row_value(row, "ts"),
                    _optional_row_value(row, "level"),
                    _optional_row_value(row, "target"),
                    _optional_row_value(row, "feedback_log_body"),
                    _json_text(row_json),
                ),
            )
            imported += 1
    return imported


def _iter_source_files(source_root: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    state_path = source_root / "state_5.sqlite"
    if state_path.exists():
        files.append((state_path, "thread_state_db"))
    logs_path = source_root / "logs_1.sqlite"
    if logs_path.exists():
        files.append((logs_path, "usage_log_db"))
    sessions_dir = source_root / "sessions"
    if sessions_dir.exists():
        files.extend((path, "session_rollout") for path in sorted(sessions_dir.rglob("*.jsonl")))
    archived_dir = source_root / "archived_sessions"
    if archived_dir.exists():
        files.extend((path, "session_rollout") for path in sorted(archived_dir.glob("*.jsonl")))
    return files


def ingest_codex_history(*, source_root: Path, warehouse_path: Path) -> IngestSummary:
    if not source_root.exists():
        raise ValueError(f"Source root does not exist: {source_root}")
    ensure_parent_dir(warehouse_path)

    scanned_files = 0
    imported_files = 0
    skipped_files = 0
    threads = 0
    sessions = 0
    projects = 0
    session_events = 0
    token_count_events = 0
    token_usage_events = 0
    input_tokens = 0
    cached_input_tokens = 0
    output_tokens = 0
    reasoning_output_tokens = 0
    total_tokens = 0
    messages = 0
    logs = 0

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        for source_path, source_kind in _iter_source_files(source_root):
            scanned_files += 1
            content_hash = _file_sha256(source_path)
            stat_result = source_path.stat()
            existing = conn.execute(
                "SELECT content_hash FROM source_manifest WHERE source_path = ?",
                (str(source_path),),
            ).fetchone()
            if existing is not None and existing["content_hash"] == content_hash:
                skipped_files += 1
                continue

            _delete_source_rows(conn, str(source_path), source_kind)
            if source_kind == "thread_state_db":
                imported_rows = _import_state_db(conn, source_path)
                threads += imported_rows
                record_count = imported_rows
            elif source_kind == "usage_log_db":
                imported_rows = _import_logs_db(conn, source_path)
                logs += imported_rows
                record_count = imported_rows
            else:
                before_sessions = conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0]
                before_events = conn.execute("SELECT count(*) FROM raw_session_events").fetchone()[0]
                before_messages = conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0]
                before_token_count_events = conn.execute("SELECT count(*) FROM raw_token_usage").fetchone()[0]
                before_token_usage_events = conn.execute(
                    "SELECT count(*) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                before_input_tokens = conn.execute(
                    "SELECT coalesce(sum(input_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                before_cached_input_tokens = conn.execute(
                    "SELECT coalesce(sum(cached_input_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                before_output_tokens = conn.execute(
                    "SELECT coalesce(sum(output_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                before_reasoning_output_tokens = conn.execute(
                    "SELECT coalesce(sum(reasoning_output_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                before_total_tokens = conn.execute(
                    "SELECT coalesce(sum(total_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                session_records = _import_session_file(conn, source_path)
                after_sessions = conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0]
                after_events = conn.execute("SELECT count(*) FROM raw_session_events").fetchone()[0]
                after_messages = conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0]
                after_token_count_events = conn.execute("SELECT count(*) FROM raw_token_usage").fetchone()[0]
                after_token_usage_events = conn.execute(
                    "SELECT count(*) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                after_input_tokens = conn.execute(
                    "SELECT coalesce(sum(input_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                after_cached_input_tokens = conn.execute(
                    "SELECT coalesce(sum(cached_input_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                after_output_tokens = conn.execute(
                    "SELECT coalesce(sum(output_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                after_reasoning_output_tokens = conn.execute(
                    "SELECT coalesce(sum(reasoning_output_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                after_total_tokens = conn.execute(
                    "SELECT coalesce(sum(total_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
                ).fetchone()[0]
                sessions += after_sessions - before_sessions
                session_events += after_events - before_events
                messages += after_messages - before_messages
                token_count_events += after_token_count_events - before_token_count_events
                token_usage_events += after_token_usage_events - before_token_usage_events
                input_tokens += after_input_tokens - before_input_tokens
                cached_input_tokens += after_cached_input_tokens - before_cached_input_tokens
                output_tokens += after_output_tokens - before_output_tokens
                reasoning_output_tokens += after_reasoning_output_tokens - before_reasoning_output_tokens
                total_tokens += after_total_tokens - before_total_tokens
                record_count = session_records
            _upsert_manifest(
                conn,
                source_path=source_path,
                source_kind=source_kind,
                content_hash=content_hash,
                size_bytes=stat_result.st_size,
                mtime_ns=stat_result.st_mtime_ns,
                record_count=record_count,
            )
            imported_files += 1
        conn.commit()

        project_rows = conn.execute(
            """
            SELECT count(DISTINCT project_cwd)
            FROM (
                SELECT cwd AS project_cwd
                FROM raw_threads
                WHERE cwd IS NOT NULL AND trim(cwd) != ''
                UNION
                SELECT cwd AS project_cwd
                FROM raw_sessions
                WHERE cwd IS NOT NULL AND trim(cwd) != ''
            )
            """
        ).fetchone()
        projects = int(project_rows[0]) if project_rows is not None and project_rows[0] is not None else 0

    return IngestSummary(
        source_root=source_root,
        warehouse_path=warehouse_path,
        scanned_files=scanned_files,
        imported_files=imported_files,
        skipped_files=skipped_files,
        projects=projects,
        threads=threads,
        sessions=sessions,
        session_events=session_events,
        token_count_events=token_count_events,
        token_usage_events=token_usage_events,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=total_tokens,
        messages=messages,
        logs=logs,
    )
