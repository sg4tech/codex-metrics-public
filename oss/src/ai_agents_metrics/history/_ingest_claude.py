"""Claude Code ingest adapter: import ~/.claude session JSONL files into the raw warehouse."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from ai_agents_metrics.history._ingest_utils import _json_text


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
        for path in sorted(project_dir.glob("*.jsonl")):
            files.append((path, "claude_session"))
        for path in sorted(project_dir.rglob("subagents/agent-*.jsonl")):
            files.append((path, "claude_session"))
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

    session_id: str | None = None
    cwd: str | None = None
    version: str | None = None
    first_timestamp: str | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
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

    if session_id is None:
        session_id = source_path.stem

    thread_id = session_id

    # INSERT OR IGNORE: subagent files share sessionId with the parent, so the
    # parent's raw_threads row is preserved unchanged when the subagent is imported.
    # The raw_threads.source_path is owned by whichever file is imported first;
    # in practice _iter_claude_source_files yields root files before subagents.
    conn.execute(
        """
        INSERT OR IGNORE INTO raw_threads (
            thread_id, source_path, updated_at, created_at, model_provider,
            model, cwd, title, first_user_message, archived, rollout_path, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id, str(source_path), None, first_timestamp, "anthropic",
            None, cwd, None, None, 0, str(source_path),
            _json_text({"session_id": session_id, "cwd": cwd}),
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
            str(source_path), str(source_path), thread_id, first_timestamp,
            cwd, "claude", "anthropic", version, "claude-code",
            _json_text({"session_id": session_id, "cwd": cwd, "version": version}),
        ),
    )

    imported = 0
    for event_index, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = str(event.get("type") or "")
        timestamp = event.get("timestamp") if isinstance(event.get("timestamp"), str) else None
        role = event_type if event_type in ("user", "assistant") else None

        event_id = hashlib.sha256(
            f"{source_path}:{event_index}:{line}".encode("utf-8")
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
        imported += 1

        token_usage = _extract_claude_token_usage(
            event,
            event_id=event_id,
            source_path=str(source_path),
            thread_id=thread_id,
            event_index=event_index,
        )
        if token_usage is not None:
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

        if event_type in ("user", "assistant"):
            message = event.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            texts = _extract_claude_message_text(content)
            for message_index, text in enumerate(texts):
                message_id = hashlib.sha256(
                    f"{source_path}:{event_index}:{message_index}:{event_type}:{text}".encode("utf-8")
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

    return imported
