"""Warehouse-side row loader for the history-compare report."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class HistoryCompareScopeRow:
    projects: int
    threads: int
    attempts: int
    retry_threads: int
    transcript_threads: int
    usage_threads: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class HistoryCompareProjectRow:
    project_cwd: str
    threads: int
    attempts: int
    retry_threads: int
    message_count: int
    usage_event_count: int
    log_count: int
    timeline_event_count: int
    total_tokens: int | None


@dataclass(frozen=True)
class HistoryCompareWarehouseData:
    global_scope: HistoryCompareScopeRow
    project_scope: HistoryCompareScopeRow
    projects: list[HistoryCompareProjectRow]


def _sum_nullable_int(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    value = row[0]
    return None if value is None else int(value)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _session_usage_table_name(conn: sqlite3.Connection) -> str:
    if _table_exists(conn, "derived_session_usage"):
        return "derived_session_usage"
    raise ValueError("Warehouse does not contain derived agent history; run history-derive first")


def _warehouse_scope_row(conn: sqlite3.Connection, *, cwd: str | None = None) -> HistoryCompareScopeRow:
    _session_usage_table_name(conn)  # validate table exists

    # Use a universal WHERE that passes through all rows when cwd is None,
    # and filters by exact cwd + worktree paths when cwd is provided.
    if cwd is not None:
        params: tuple[Any, ...] = (cwd, cwd, cwd + "/.claude/worktrees/%")
    else:
        params = (None, None, None)

    thread_count = int(conn.execute(
        "SELECT count(*) FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?)", params,
    ).fetchone()[0])
    attempt_count = int(conn.execute(
        "SELECT coalesce(sum(attempt_count), 0) FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?)", params,
    ).fetchone()[0])
    retry_threads = int(conn.execute(
        "SELECT count(*) FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?) AND retry_count > 0", params,
    ).fetchone()[0])
    transcript_threads = int(conn.execute(
        "SELECT count(*) FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?) AND message_count > 0", params,
    ).fetchone()[0])
    usage_threads = int(conn.execute(
        "SELECT count(DISTINCT thread_id) FROM derived_session_usage"
        " WHERE thread_id IN (SELECT thread_id FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?))"
        " AND total_tokens IS NOT NULL", params,
    ).fetchone()[0])
    input_tokens = _sum_nullable_int(conn,
        "SELECT sum(input_tokens) FROM derived_session_usage"
        " WHERE thread_id IN (SELECT thread_id FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?))", params)
    cached_input_tokens = _sum_nullable_int(conn,
        "SELECT sum(cached_input_tokens) FROM derived_session_usage"
        " WHERE thread_id IN (SELECT thread_id FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?))", params)
    output_tokens = _sum_nullable_int(conn,
        "SELECT sum(output_tokens) FROM derived_session_usage"
        " WHERE thread_id IN (SELECT thread_id FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?))", params)
    total_tokens = _sum_nullable_int(conn,
        "SELECT sum(total_tokens) FROM derived_session_usage"
        " WHERE thread_id IN (SELECT thread_id FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?))", params)
    if _table_exists(conn, "derived_projects"):
        projects_columns = {row[1] for row in conn.execute("PRAGMA table_info(derived_projects)").fetchall()}
        has_parent_col = "parent_project_cwd" in projects_columns
        if cwd is not None:
            if has_parent_col:
                project_count = int(
                    conn.execute(
                        "SELECT count(*) FROM derived_projects WHERE parent_project_cwd = ?",
                        (cwd,),
                    ).fetchone()[0]
                )
            else:
                project_count = int(
                    conn.execute(
                        "SELECT count(*) FROM derived_projects WHERE project_cwd = ?",
                        (cwd,),
                    ).fetchone()[0]
                )
        else:
            project_count = int(conn.execute("SELECT count(*) FROM derived_projects").fetchone()[0])
    else:
        if cwd is not None:
            project_count = int(conn.execute(
                "SELECT count(DISTINCT cwd) FROM derived_goals WHERE (? IS NULL OR cwd = ? OR cwd LIKE ?)", params,
            ).fetchone()[0])
        else:
            project_count = int(
                conn.execute(
                    "SELECT count(DISTINCT cwd) FROM derived_goals WHERE cwd IS NOT NULL AND trim(cwd) != ''",
                ).fetchone()[0]
            )
    return HistoryCompareScopeRow(
        projects=project_count,
        threads=thread_count,
        attempts=attempt_count,
        retry_threads=retry_threads,
        transcript_threads=transcript_threads,
        usage_threads=usage_threads,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _load_project_rows(conn: sqlite3.Connection) -> list[HistoryCompareProjectRow]:
    if not _table_exists(conn, "derived_projects"):
        return []
    project_rows = conn.execute(
        """
        SELECT project_cwd, thread_count, attempt_count, retry_thread_count,
               message_count, usage_event_count, log_count, timeline_event_count, total_tokens
        FROM derived_projects
        ORDER BY thread_count DESC, attempt_count DESC, project_cwd ASC
        """
    ).fetchall()
    return [
        HistoryCompareProjectRow(
            project_cwd=row["project_cwd"],
            threads=int(row["thread_count"]),
            attempts=int(row["attempt_count"]),
            retry_threads=int(row["retry_thread_count"]),
            message_count=int(row["message_count"]),
            usage_event_count=int(row["usage_event_count"]),
            log_count=int(row["log_count"]),
            timeline_event_count=int(row["timeline_event_count"]),
            total_tokens=None if row["total_tokens"] is None else int(row["total_tokens"]),
        )
        for row in project_rows
    ]


def load_history_compare_warehouse_data(*, warehouse_path: Path, cwd: Path) -> HistoryCompareWarehouseData:
    if not warehouse_path.exists():
        raise ValueError(
            f"Warehouse does not exist: {warehouse_path}. "
            "Run 'ai-agents-metrics history-update' first."
        )

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("SELECT 1 FROM derived_goals LIMIT 1").fetchone()
            _session_usage_table_name(conn)
        except sqlite3.OperationalError as exc:
            raise ValueError(
                "Warehouse does not contain derived agent history; run history-derive first"
            ) from exc

        global_scope = _warehouse_scope_row(conn)
        project_scope = _warehouse_scope_row(conn, cwd=str(cwd.resolve()))
        projects = _load_project_rows(conn)

    return HistoryCompareWarehouseData(
        global_scope=global_scope,
        project_scope=project_scope,
        projects=projects,
    )
