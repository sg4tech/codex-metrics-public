"""Codex adapter: convert ~/.codex state/logs/sessions into raw_* rows."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.history.ingest.warehouse import (
    _json_text,
    _optional_row_value,
)

if TYPE_CHECKING:
    from pathlib import Path


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
