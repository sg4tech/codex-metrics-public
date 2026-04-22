"""Ingest stage: ~/.codex and ~/.claude on-disk history → raw_* warehouse tables."""
# pylint: disable=too-many-lines  # ingest.py handles all history ingestion stages; split into sub-stages is a tracked future task
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain import now_utc_iso
from ai_agents_metrics.storage import ensure_parent_dir

if TYPE_CHECKING:
    from pathlib import Path

RAW_WAREHOUSE_DIRNAME = ".ai-agents-metrics"
_RAW_WAREHOUSE_DIRNAME_LEGACY = ".codex-metrics"
RAW_WAREHOUSE_FILENAME = "warehouse.db"


# IngestSummary is a canonical count-and-path record shown in ingest reports.
# Each field corresponds to a surfaced counter, so grouping into nested
# structs would break reporting output.
@dataclass(frozen=True)
class IngestSummary:  # pylint: disable=too-many-instance-attributes
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
        return row[key] if key in row.keys() else default  # noqa: SIM118 sqlite3.Row lacks .get()
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
            event_id = hashlib.sha256(f"{source_path}:{event_index}:{line}".encode()).hexdigest()
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
                            f"{source_path}:{event_index}:{message_index}:{role}:{text}".encode()
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


# ---------------------------------------------------------------------------
# Claude Code adapter
# ---------------------------------------------------------------------------

def _encode_claude_cwd(cwd: str) -> str:
    """Encode a filesystem path to the Claude project directory name format."""
    return cwd.replace("/", "-")


def _iter_claude_source_files(claude_root: Path, cwd_filter: str | None = None) -> list[tuple[Path, str]]:
    """Iterate Claude Code session JSONL files from ~/.claude/projects/.

    Args:
        claude_root: Path to the Claude root directory (e.g. ``~/.claude``).
        cwd_filter: If given, only scan the project directory whose encoded name
            matches this cwd (i.e. ``_encode_claude_cwd(cwd_filter)``).
    """
    files: list[tuple[Path, str]] = []
    projects_dir = claude_root / "projects"
    if not projects_dir.exists():
        return files
    encoded_filter = _encode_claude_cwd(cwd_filter) if cwd_filter is not None else None
    for project_dir in sorted(d for d in projects_dir.iterdir() if d.is_dir()):
        if encoded_filter is not None and project_dir.name != encoded_filter:
            continue
        files.extend((path, "claude_session") for path in sorted(project_dir.glob("*.jsonl")))
        files.extend((path, "claude_session") for path in sorted(project_dir.rglob("subagents/agent-*.jsonl")))
    return files



def _extract_claude_message_text(content: Any) -> list[str]:
    """Extract text segments from a Claude Code message content array."""
    texts: list[str] = []
    if not isinstance(content, list):
        return texts
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts


def _extract_claude_token_usage(
    event: dict[str, Any],
    *,
    event_id: str,
    source_path: str,
    thread_id: str | None,
    event_index: int,
) -> dict[str, Any] | None:
    """Extract token usage from a Claude Code assistant event."""
    if event.get("type") != "assistant":
        return None
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = int(usage.get("input_tokens") or 0)
    cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total = input_tokens + cache_creation + cache_read + output_tokens

    if total == 0:
        return None

    timestamp = event.get("timestamp") if isinstance(event.get("timestamp"), str) else None
    model = message.get("model")

    return {
        "token_event_id": event_id,
        "session_path": source_path,
        "source_path": source_path,
        "thread_id": thread_id,
        "event_index": event_index,
        "timestamp": timestamp,
        "has_breakdown": 1,
        "input_tokens": input_tokens,
        # cache_creation: writing new cache entries (billed at ~1.25× normal input rate)
        "cache_creation_input_tokens": cache_creation,
        # cache_read: reading existing cache entries (billed at ~0.1× normal input rate)
        "cached_input_tokens": cache_read,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": None,
        "total_tokens": total,
        "model": model,
        "raw_json": _json_text(event),
    }


@dataclass(frozen=True)
class _ClaudeSessionHeader:
    session_id: str
    cwd: str | None
    version: str | None
    first_timestamp: str | None


def _parse_claude_session_header(lines: list[str], fallback_session_id: str) -> _ClaudeSessionHeader:
    session_id: str | None = None
    cwd: str | None = None
    version: str | None = None
    first_timestamp: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if session_id is None:
            session_id = event.get("sessionId")
        if cwd is None:
            cwd = event.get("cwd")
        if version is None:
            version = event.get("version")
        ts = event.get("timestamp")
        if isinstance(ts, str) and first_timestamp is None:
            first_timestamp = ts
        if session_id and cwd:
            break
    return _ClaudeSessionHeader(
        session_id=session_id or fallback_session_id,
        cwd=cwd,
        version=version,
        first_timestamp=first_timestamp,
    )


def _insert_claude_session_and_thread(
    conn: sqlite3.Connection,
    source_path: Path,
    header: _ClaudeSessionHeader,
) -> None:
    # INSERT OR IGNORE: subagent files share sessionId with the parent, so the
    # parent's raw_threads row is preserved unchanged when the subagent is imported.
    conn.execute(
        """
        INSERT OR IGNORE INTO raw_threads (
            thread_id, source_path, updated_at, created_at, model_provider,
            model, cwd, title, first_user_message, archived, rollout_path, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            header.session_id, str(source_path), None, header.first_timestamp, "anthropic",
            None, header.cwd, None, None, 0, str(source_path),
            _json_text({"session_id": header.session_id, "cwd": header.cwd}),
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO raw_sessions (
            session_path, source_path, thread_id, session_timestamp,
            cwd, source, model_provider, cli_version, originator, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(source_path), str(source_path), header.session_id, header.first_timestamp,
            header.cwd, "claude", "anthropic", header.version, "claude-code",
            _json_text({"session_id": header.session_id, "cwd": header.cwd, "version": header.version}),
        ),
    )


def _insert_claude_token_usage_row(
    conn: sqlite3.Connection, token_usage: dict[str, Any]
) -> None:
    conn.execute(
        """
        INSERT INTO raw_token_usage (
            token_event_id, session_path, source_path, thread_id, event_index,
            timestamp, has_breakdown, input_tokens, cache_creation_input_tokens,
            cached_input_tokens, output_tokens, reasoning_output_tokens,
            total_tokens, model, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_usage["token_event_id"], token_usage["session_path"],
            token_usage["source_path"], token_usage["thread_id"],
            token_usage["event_index"], token_usage["timestamp"],
            token_usage["has_breakdown"], token_usage["input_tokens"],
            token_usage["cache_creation_input_tokens"],
            token_usage["cached_input_tokens"], token_usage["output_tokens"],
            token_usage["reasoning_output_tokens"], token_usage["total_tokens"],
            token_usage["model"], token_usage["raw_json"],
        ),
    )


def _insert_claude_message_rows(
    conn: sqlite3.Connection,
    event: dict[str, Any],
    *,
    source_path: Path,
    thread_id: str,
    event_index: int,
    event_type: str,
) -> None:
    message = event.get("message", {})
    content = message.get("content", []) if isinstance(message, dict) else []
    texts = _extract_claude_message_text(content)
    for message_index, text in enumerate(texts):
        message_id = hashlib.sha256(
            f"{source_path}:{event_index}:{message_index}:{event_type}:{text}".encode()
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO raw_messages (
                message_id, session_path, source_path, thread_id, event_index,
                message_index, role, text, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id, str(source_path), str(source_path), thread_id,
                event_index, message_index, event_type, text,
                _json_text(message),
            ),
        )


def _ingest_claude_session_event(
    conn: sqlite3.Connection,
    *,
    event: dict[str, Any],
    event_index: int,
    raw_line: str,
    source_path: Path,
    thread_id: str,
) -> None:
    event_type = str(event.get("type") or "")
    timestamp = event.get("timestamp") if isinstance(event.get("timestamp"), str) else None
    role = event_type if event_type in ("user", "assistant") else None

    event_id = hashlib.sha256(
        f"{source_path}:{event_index}:{raw_line}".encode()
    ).hexdigest()

    conn.execute(
        """
        INSERT INTO raw_session_events (
            event_id, session_path, source_path, thread_id, event_index,
            event_type, timestamp, payload_type, role, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, str(source_path), str(source_path), thread_id, event_index,
            event_type, timestamp, None, role, _json_text(event),
        ),
    )

    token_usage = _extract_claude_token_usage(
        event,
        event_id=event_id,
        source_path=str(source_path),
        thread_id=thread_id,
        event_index=event_index,
    )
    if token_usage is not None:
        _insert_claude_token_usage_row(conn, token_usage)

    if event_type in ("user", "assistant"):
        _insert_claude_message_rows(
            conn, event,
            source_path=source_path,
            thread_id=thread_id,
            event_index=event_index,
            event_type=event_type,
        )


def _import_claude_session_file(conn: sqlite3.Connection, source_path: Path) -> int:
    """Import a Claude Code session JSONL file into the raw warehouse.

    Thread identity: sessionId from events is used directly as thread_id.
    Each top-level .jsonl file is a separate conversation (thread). Subagent
    files (subagents/agent-*.jsonl) share the parent sessionId and are grouped
    into the same thread via INSERT OR IGNORE on raw_threads.
    """
    conn.execute("DELETE FROM raw_threads WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_sessions WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_session_events WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_messages WHERE source_path = ?", (str(source_path),))
    conn.execute("DELETE FROM raw_token_usage WHERE source_path = ?", (str(source_path),))

    with source_path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    header = _parse_claude_session_header(lines, fallback_session_id=source_path.stem)
    _insert_claude_session_and_thread(conn, source_path, header)

    imported = 0
    for event_index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        _ingest_claude_session_event(
            conn,
            event=event,
            event_index=event_index,
            raw_line=stripped,
            source_path=source_path,
            thread_id=header.session_id,
        )
        imported += 1

    return imported


# _IngestTotals mirrors the set of counters surfaced in IngestSummary; each
# field is an independent counter reported to the CLI.
@dataclass
class _IngestTotals:  # pylint: disable=too-many-instance-attributes
    threads: int = 0
    sessions: int = 0
    session_events: int = 0
    token_count_events: int = 0
    token_usage_events: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    messages: int = 0
    logs: int = 0


# _WarehouseSnapshot mirrors the raw-warehouse counter set consumed by
# _accumulate_snapshot_delta; each field is an independent counter.
@dataclass(frozen=True)
class _WarehouseSnapshot:  # pylint: disable=too-many-instance-attributes
    threads: int = 0
    sessions: int = 0
    session_events: int = 0
    messages: int = 0
    token_count_events: int = 0
    token_usage_events: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0


def _snapshot_warehouse(conn: sqlite3.Connection, *, include_reasoning: bool) -> _WarehouseSnapshot:
    """Capture the row/sum counters used to derive per-file import deltas."""

    def _scalar(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    return _WarehouseSnapshot(
        threads=_scalar("SELECT count(*) FROM raw_threads"),
        sessions=_scalar("SELECT count(*) FROM raw_sessions"),
        session_events=_scalar("SELECT count(*) FROM raw_session_events"),
        messages=_scalar("SELECT count(*) FROM raw_messages"),
        token_count_events=_scalar("SELECT count(*) FROM raw_token_usage"),
        token_usage_events=_scalar(
            "SELECT count(*) FROM raw_token_usage WHERE has_breakdown = 1"
        ),
        input_tokens=_scalar(
            "SELECT coalesce(sum(input_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
        ),
        cached_input_tokens=_scalar(
            "SELECT coalesce(sum(cached_input_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
        ),
        output_tokens=_scalar(
            "SELECT coalesce(sum(output_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
        ),
        reasoning_output_tokens=(
            _scalar(
                "SELECT coalesce(sum(reasoning_output_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
            )
            if include_reasoning
            else 0
        ),
        total_tokens=_scalar(
            "SELECT coalesce(sum(total_tokens), 0) FROM raw_token_usage WHERE has_breakdown = 1"
        ),
    )


def _accumulate_snapshot_delta(
    totals: _IngestTotals,
    before: _WarehouseSnapshot,
    after: _WarehouseSnapshot,
    *,
    include_reasoning: bool,
    include_token_count_events: bool,
) -> None:
    totals.threads += after.threads - before.threads
    totals.sessions += after.sessions - before.sessions
    totals.session_events += after.session_events - before.session_events
    totals.messages += after.messages - before.messages
    totals.token_usage_events += after.token_usage_events - before.token_usage_events
    totals.input_tokens += after.input_tokens - before.input_tokens
    totals.cached_input_tokens += after.cached_input_tokens - before.cached_input_tokens
    totals.output_tokens += after.output_tokens - before.output_tokens
    totals.total_tokens += after.total_tokens - before.total_tokens
    if include_reasoning:
        totals.reasoning_output_tokens += (
            after.reasoning_output_tokens - before.reasoning_output_tokens
        )
    if include_token_count_events:
        totals.token_count_events += after.token_count_events - before.token_count_events


def _count_distinct_projects(conn: sqlite3.Connection) -> int:
    row = conn.execute(
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
    return int(row[0]) if row is not None and row[0] is not None else 0


def ingest_codex_history(
    *,
    source_root: Path,
    warehouse_path: Path,
    source: str = "codex",
) -> IngestSummary:
    """Ingest agent history into the raw warehouse.

    Args:
        source_root: Root directory to read from. For ``"codex"`` this is
            ``~/.codex``; for ``"claude"`` this is ``~/.claude``.
        warehouse_path: SQLite warehouse path.
        source: Agent source — ``"codex"`` (default) or ``"claude"``.

    Raises:
        ValueError: If ``source`` is not a recognised value or ``source_root``
            does not exist.
    """
    if source not in ("codex", "claude"):
        raise ValueError(f"Unknown source {source!r}; expected 'codex' or 'claude'")
    if not source_root.exists():
        raise ValueError(f"Source root does not exist: {source_root}")
    ensure_parent_dir(warehouse_path)

    scanned_files = 0
    imported_files = 0
    skipped_files = 0
    totals = _IngestTotals()

    source_files = (
        _iter_claude_source_files(source_root)
        if source == "claude"
        else _iter_source_files(source_root)
    )

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        for source_path, source_kind in source_files:
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
            record_count = _import_source_and_update_totals(
                conn, source_path, source_kind, totals
            )
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

        projects = _count_distinct_projects(conn)

    return IngestSummary(
        source_root=source_root,
        warehouse_path=warehouse_path,
        scanned_files=scanned_files,
        imported_files=imported_files,
        skipped_files=skipped_files,
        projects=projects,
        threads=totals.threads,
        sessions=totals.sessions,
        session_events=totals.session_events,
        token_count_events=totals.token_count_events,
        token_usage_events=totals.token_usage_events,
        input_tokens=totals.input_tokens,
        cached_input_tokens=totals.cached_input_tokens,
        output_tokens=totals.output_tokens,
        reasoning_output_tokens=totals.reasoning_output_tokens,
        total_tokens=totals.total_tokens,
        messages=totals.messages,
        logs=totals.logs,
    )


def _import_source_and_update_totals(
    conn: sqlite3.Connection,
    source_path: Path,
    source_kind: str,
    totals: _IngestTotals,
) -> int:
    """Dispatch to the right per-source-kind importer; update *totals* in place."""
    if source_kind == "thread_state_db":
        imported_rows = _import_state_db(conn, source_path)
        totals.threads += imported_rows
        return imported_rows
    if source_kind == "usage_log_db":
        imported_rows = _import_logs_db(conn, source_path)
        totals.logs += imported_rows
        return imported_rows
    if source_kind == "claude_session":
        before = _snapshot_warehouse(conn, include_reasoning=False)
        session_records = _import_claude_session_file(conn, source_path)
        after = _snapshot_warehouse(conn, include_reasoning=False)
        _accumulate_snapshot_delta(
            totals, before, after,
            include_reasoning=False,
            include_token_count_events=False,
        )
        return session_records
    # Codex default path: includes reasoning_output_tokens and token_count_events.
    before = _snapshot_warehouse(conn, include_reasoning=True)
    session_records = _import_session_file(conn, source_path)
    after = _snapshot_warehouse(conn, include_reasoning=True)
    _accumulate_snapshot_delta(
        totals, before, after,
        include_reasoning=True,
        include_token_count_events=True,
    )
    return session_records


def render_ingest_summary_json(summary: IngestSummary) -> str:
    return json.dumps({
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
    })
