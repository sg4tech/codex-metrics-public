"""SQLite event store and debug log for CLI-invocation observability."""
from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain import now_utc_iso
from ai_agents_metrics.redaction import redact_text, redact_value
from ai_agents_metrics.storage import ensure_parent_dir

if TYPE_CHECKING:
    from pathlib import Path

OBSERVABILITY_DIRNAME = ".ai-agents-metrics"
_OBSERVABILITY_DIRNAME_LEGACY = ".codex-metrics"
EVENT_STORE_FILENAME = "events.sqlite"
EVENT_DEBUG_LOG_FILENAME = "events.debug.log"


@dataclass(frozen=True)
class ObservabilityPaths:
    event_store_path: Path
    debug_log_path: Path


@dataclass(frozen=True)
class EventContext:
    """Metadata describing an observability event's source goal/command.

    Groups the recurring fields that otherwise inflate helper signatures
    past pylint's too-many-arguments threshold.
    """

    command: str | None
    goal_id: str | None
    goal_type: str | None
    status_before: str | None
    status_after: str | None
    attempts_before: int | None
    attempts_after: int | None
    result_fit_before: str | None
    result_fit_after: str | None


def observability_paths(metrics_path: Path) -> ObservabilityPaths:
    legacy_dir = metrics_path.parent / _OBSERVABILITY_DIRNAME_LEGACY
    observability_dir = legacy_dir if legacy_dir.exists() else metrics_path.parent / OBSERVABILITY_DIRNAME
    return ObservabilityPaths(
        event_store_path=observability_dir / EVENT_STORE_FILENAME,
        debug_log_path=observability_dir / EVENT_DEBUG_LOG_FILENAME,
    )


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _debug_field(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _build_debug_line(
    *,
    event_id: str,
    event_type: str,
    occurred_at: str,
    source: str,
    context: EventContext,
    payload: dict[str, Any],
) -> str:
    parts = [
        f"occurred_at={_debug_field(occurred_at)}",
        f"event_id={_debug_field(event_id)}",
        f"event_type={_debug_field(event_type)}",
        f"source={_debug_field(source)}",
    ]
    if context.command is not None:
        parts.append(f"command={_debug_field(context.command)}")
    if context.goal_id is not None:
        parts.append(f"goal_id={_debug_field(context.goal_id)}")
    if context.goal_type is not None:
        parts.append(f"goal_type={_debug_field(context.goal_type)}")
    if context.status_before is not None:
        parts.append(f"status_before={_debug_field(context.status_before)}")
    if context.status_after is not None:
        parts.append(f"status_after={_debug_field(context.status_after)}")
    if context.attempts_before is not None:
        parts.append(f"attempts_before={context.attempts_before}")
    if context.attempts_after is not None:
        parts.append(f"attempts_after={context.attempts_after}")
    if context.result_fit_before is not None:
        parts.append(f"result_fit_before={_debug_field(context.result_fit_before)}")
    if context.result_fit_after is not None:
        parts.append(f"result_fit_after={_debug_field(context.result_fit_after)}")
    if payload:
        parts.append(f"payload={_debug_field(payload)}")
    return " ".join(parts)


def _ensure_event_store_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            command TEXT,
            goal_id TEXT,
            goal_type TEXT,
            status_before TEXT,
            status_after TEXT,
            attempts_before INTEGER,
            attempts_after INTEGER,
            result_fit_before TEXT,
            result_fit_after TEXT,
            payload_json TEXT NOT NULL,
            debug_line TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_type_goal ON events(event_type, goal_id)"
    )


def _append_debug_line(debug_log_path: Path, debug_line: str) -> None:
    ensure_parent_dir(debug_log_path)
    with debug_log_path.open("a", encoding="utf-8") as debug_log:
        debug_log.write(debug_line)
        debug_log.write("\n")


def _store_event(
    *,
    metrics_path: Path,
    event_type: str,
    payload: dict[str, Any],
    context: EventContext,
) -> str:
    paths = observability_paths(metrics_path)
    event_id = uuid.uuid4().hex
    occurred_at = now_utc_iso()
    redacted_payload = redact_value(payload)
    payload_json = _json_text(redacted_payload)
    debug_line = _build_debug_line(
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        source="codex-metrics",
        context=context,
        payload=redacted_payload,
    )
    ensure_parent_dir(paths.event_store_path)
    with sqlite3.connect(paths.event_store_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_event_store_schema(conn)
        conn.execute(
            """
            INSERT INTO events (
                event_id,
                occurred_at,
                event_type,
                source,
                command,
                goal_id,
                goal_type,
                status_before,
                status_after,
                attempts_before,
                attempts_after,
                result_fit_before,
                result_fit_after,
                payload_json,
                debug_line
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                occurred_at,
                event_type,
                "codex-metrics",
                context.command,
                context.goal_id,
                context.goal_type,
                context.status_before,
                context.status_after,
                context.attempts_before,
                context.attempts_after,
                context.result_fit_before,
                context.result_fit_after,
                payload_json,
                debug_line,
            ),
        )
        conn.commit()
    _append_debug_line(paths.debug_log_path, debug_line)
    return event_id


def _record_event_best_effort(
    *,
    metrics_path: Path,
    event_type: str,
    payload: dict[str, Any],
    context: EventContext,
) -> None:
    try:
        _store_event(
            metrics_path=metrics_path,
            event_type=event_type,
            payload=payload,
            context=context,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        paths = observability_paths(metrics_path)
        fallback_payload = {
            "error": type(exc).__name__,
            "message": redact_text(str(exc)),
            "event_type": event_type,
            "goal_id": context.goal_id,
            "command": context.command,
        }
        fallback_line = _build_debug_line(
            event_id=uuid.uuid4().hex,
            event_type="observability_write_failed",
            occurred_at=now_utc_iso(),
            source="codex-metrics",
            context=context,
            payload=fallback_payload,
        )
        with contextlib.suppress(Exception):  # nosec B110  # pylint: disable=broad-exception-caught
            _append_debug_line(paths.debug_log_path, fallback_line)


def record_cli_invocation_observation(
    metrics_path: Path,
    *,
    command: str,
    cwd: str,
    task_id: str | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "command": command,
        "cwd": cwd,
    }
    if task_id is not None:
        payload["task_id"] = task_id
    if extra_payload:
        payload.update(extra_payload)
    _record_event_best_effort(
        metrics_path=metrics_path,
        event_type="cli_invoked",
        payload=payload,
        context=EventContext(
            command=command,
            goal_id=task_id,
            goal_type=None,
            status_before=None,
            status_after=None,
            attempts_before=None,
            attempts_after=None,
            result_fit_before=None,
            result_fit_after=None,
        ),
    )


def _changed_fields(previous_task: dict[str, Any] | None, current_task: dict[str, Any]) -> list[str]:
    if previous_task is None:
        return sorted(
            field
            for field in (
                "title",
                "goal_type",
                "status",
                "attempts",
                "started_at",
                "finished_at",
                "cost_usd",
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "tokens_total",
                "failure_reason",
                "notes",
                "agent_name",
                "result_fit",
                "model",
            )
            if current_task.get(field) is not None
        )

    return [
        field
        for field in (
            "title",
            "goal_type",
            "status",
            "attempts",
            "started_at",
            "finished_at",
            "cost_usd",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "tokens_total",
            "failure_reason",
            "notes",
            "agent_name",
            "result_fit",
            "model",
            "supersedes_goal_id",
        )
        if previous_task.get(field) != current_task.get(field)
    ]


def _classify_goal_event(previous_task: dict[str, Any] | None, current_task: dict[str, Any]) -> str:
    if previous_task is None:
        return "goal_created"
    previous_status = previous_task.get("status")
    current_status = current_task.get("status")
    previous_attempts = int(previous_task.get("attempts") or 0)
    current_attempts = int(current_task.get("attempts") or 0)
    if previous_status != current_status and current_status in {"success", "fail"}:
        return "goal_closed"
    if current_attempts > previous_attempts:
        return "goal_attempt_incremented"
    if previous_task.get("goal_type") != current_task.get("goal_type") or previous_task.get("title") != current_task.get("title"):
        return "goal_updated"
    return "goal_updated"


def record_goal_mutation_observation(
    metrics_path: Path,
    *,
    command: str,
    previous_task: dict[str, Any] | None,
    current_task: dict[str, Any],
) -> None:
    event_type = _classify_goal_event(previous_task, current_task)
    payload = {
        "command": command,
        "changed_fields": _changed_fields(previous_task, current_task),
        "goal_id": current_task.get("goal_id"),
        "goal_type": current_task.get("goal_type"),
        "attempts_before": None if previous_task is None else previous_task.get("attempts"),
        "attempts_after": current_task.get("attempts"),
        "status_before": None if previous_task is None else previous_task.get("status"),
        "status_after": current_task.get("status"),
        "result_fit_before": None if previous_task is None else previous_task.get("result_fit"),
        "result_fit_after": current_task.get("result_fit"),
    }
    _record_event_best_effort(
        metrics_path=metrics_path,
        event_type=event_type,
        payload=payload,
        context=EventContext(
            command=command,
            goal_id=current_task.get("goal_id"),
            goal_type=current_task.get("goal_type"),
            status_before=None if previous_task is None else previous_task.get("status"),
            status_after=current_task.get("status"),
            attempts_before=None if previous_task is None else int(previous_task.get("attempts") or 0),
            attempts_after=int(current_task.get("attempts") or 0),
            result_fit_before=None if previous_task is None else previous_task.get("result_fit"),
            result_fit_after=current_task.get("result_fit"),
        ),
    )


def record_usage_sync_observation(
    metrics_path: Path,
    *,
    command: str,
    updated_tasks: int,
    usage_backend: str | None,
    usage_thread_id: str | None,
) -> None:
    payload = {
        "command": command,
        "updated_tasks": updated_tasks,
        "usage_backend": usage_backend,
        "usage_thread_id": usage_thread_id,
    }
    _record_event_best_effort(
        metrics_path=metrics_path,
        event_type="usage_synced",
        payload=payload,
        context=EventContext(
            command=command,
            goal_id=None,
            goal_type=None,
            status_before=None,
            status_after=None,
            attempts_before=None,
            attempts_after=None,
            result_fit_before=None,
            result_fit_after=None,
        ),
    )


def record_goal_merge_observation(
    metrics_path: Path,
    *,
    command: str,
    keep_task_id: str,
    drop_task_id: str,
    merged_task: dict[str, Any],
) -> None:
    payload = {
        "command": command,
        "keep_task_id": keep_task_id,
        "drop_task_id": drop_task_id,
        "merged_attempts": merged_task.get("attempts"),
        "merged_status": merged_task.get("status"),
    }
    _record_event_best_effort(
        metrics_path=metrics_path,
        event_type="goal_merged",
        payload=payload,
        context=EventContext(
            command=command,
            goal_id=keep_task_id,
            goal_type=merged_task.get("goal_type"),
            status_before=None,
            status_after=merged_task.get("status"),
            attempts_before=None,
            attempts_after=int(merged_task.get("attempts") or 0),
            result_fit_before=None,
            result_fit_after=merged_task.get("result_fit"),
        ),
    )
