from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_agents_metrics.history_derive_build import (
    _build_index_maps,
    _build_message_usage_groups,
    _build_timeline_items,
    _fetch_normalized_logs,
    _fetch_normalized_messages,
    _fetch_normalized_sessions,
    _fetch_normalized_threads,
    _fetch_normalized_usage_events,
    _normalize_timestamp,
    _parent_project_cwd,
    _pick_earliest_timestamp,
    _pick_latest_timestamp,
)
from ai_agents_metrics.history_derive_insert import (
    _insert_attempts_and_session_usage,
    _insert_goal_and_retry_chain,
    _insert_message_facts,
    _insert_projects,
    _insert_timeline_events,
)
from ai_agents_metrics.history_derive_schema import (
    _clear_derived_tables,
    _ensure_schema,
)


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


def derive_codex_history(*, warehouse_path: Path) -> DeriveSummary:
    if not warehouse_path.exists():
        raise ValueError(
            f"Warehouse does not exist: {warehouse_path}. "
            "Run 'ai-agents-metrics history-update' first."
        )

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
                "Warehouse does not contain normalized Codex history; run history-normalize first"
            ) from exc
        except IndexError as exc:
            raise ValueError(
                "Warehouse schema is incompatible with this version of codex-metrics; "
                "run history-normalize first"
            ) from exc

        (
            sessions_by_thread,
            messages_by_session,
            messages_by_thread,
            usage_events_by_session,
            usage_events_by_thread,
            logs_by_thread,
        ) = _build_index_maps(normalized_sessions, normalized_messages, normalized_usage_events, normalized_logs)

        _clear_derived_tables(conn)
        message_usage_groups = _build_message_usage_groups(messages_by_session, usage_events_by_session)

        project_stats: dict[str, dict[str, Any]] = {}

        def get_project_stats(cwd: str) -> dict[str, Any]:
            if cwd not in project_stats:
                project_stats[cwd] = {
                    "thread_count": 0, "attempt_count": 0, "retry_thread_count": 0,
                    "message_count": 0, "usage_event_count": 0, "log_count": 0,
                    "timeline_event_count": 0, "input_tokens": 0,
                    "cache_creation_input_tokens": 0, "cached_input_tokens": 0,
                    "output_tokens": 0, "total_tokens": 0,
                    "first_seen_at": None, "last_seen_at": None,
                }
            return project_stats[cwd]

        for thread_row in normalized_threads:
            thread_id = thread_row["thread_id"]
            project_cwd = _parent_project_cwd(thread_row["cwd"])
            thread_sessions = sessions_by_thread.get(thread_id, [])
            thread_messages = messages_by_thread.get(thread_id, [])
            thread_usage_events = usage_events_by_thread.get(thread_id, [])
            thread_logs = logs_by_thread.get(thread_id, [])

            if project_cwd is not None:
                stats = get_project_stats(project_cwd)
                stats["thread_count"] += 1
                stats["attempt_count"] += int(thread_row["session_count"] or 0)
                stats["retry_thread_count"] += 1 if int(thread_row["session_count"] or 0) > 1 else 0
                stats["message_count"] += int(thread_row["message_count"] or 0)
                stats["log_count"] += int(thread_row["log_count"] or 0)
                stats["usage_event_count"] += len(thread_usage_events)
                stats["first_seen_at"] = _pick_earliest_timestamp(stats["first_seen_at"], thread_row["first_seen_at"])
                stats["last_seen_at"] = _pick_latest_timestamp(stats["last_seen_at"], thread_row["last_seen_at"])

            timeline_items = _build_timeline_items(
                thread_id, thread_sessions, thread_messages, thread_usage_events, thread_logs
            )

            if project_cwd is not None:
                get_project_stats(project_cwd)["timeline_event_count"] += len(timeline_items)

            timeline_events += _insert_timeline_events(conn, thread_id, timeline_items)
            message_facts += _insert_message_facts(
                conn, thread_id, thread_row, thread_messages, thread_sessions, message_usage_groups
            )

            sorted_sessions = sorted(
                thread_sessions,
                key=lambda row: (
                    1 if _normalize_timestamp(row["session_timestamp"]) is None else 0,
                    _normalize_timestamp(row["session_timestamp"]) or "",
                    row["session_path"],
                ),
            )
            session_usage += _insert_attempts_and_session_usage(
                conn,
                thread_id,
                sorted_sessions,
                usage_events_by_session,
                get_project_stats(project_cwd) if project_cwd is not None else None,
            )
            _insert_goal_and_retry_chain(
                conn, thread_id, thread_row, sorted_sessions, thread_usage_events, timeline_items
            )
            goals += 1
            attempts += len(sorted_sessions)
            retry_chains += 1

        projects = _insert_projects(conn, project_stats)
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


def render_derive_summary_json(summary: DeriveSummary) -> str:
    return json.dumps({
        "warehouse_path": str(summary.warehouse_path),
        "projects": summary.projects,
        "goals": summary.goals,
        "attempts": summary.attempts,
        "timeline_events": summary.timeline_events,
        "retry_chains": summary.retry_chains,
        "message_facts": summary.message_facts,
        "session_usage": summary.session_usage,
    })
