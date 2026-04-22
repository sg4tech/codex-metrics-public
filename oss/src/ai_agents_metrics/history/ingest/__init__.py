"""Ingest stage: ~/.codex and ~/.claude on-disk history → raw_* warehouse tables.

Submodule layout:
  - warehouse: schema + SQL helpers + path resolution
  - codex: Codex adapter (state/logs/sessions)
  - claude: Claude Code adapter (session JSONL)
  - __init__ (this file): orchestration + public API + test-facing re-exports

The public surface (``IngestSummary``, ``default_raw_warehouse_path``,
``ingest_codex_history``, ``render_ingest_summary_json``) is re-exported so
that ``from ai_agents_metrics.history.ingest import X`` keeps resolving for
every external consumer.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_agents_metrics.history.ingest.claude import (
    _encode_claude_cwd,
    _extract_claude_message_text,
    _extract_claude_token_usage,
    _import_claude_session_file,
    _iter_claude_source_files,
)
from ai_agents_metrics.history.ingest.codex import (
    _extract_message_text,
    _extract_token_usage,
    _import_logs_db,
    _import_session_file,
    _import_state_db,
    _iter_source_files,
)
from ai_agents_metrics.history.ingest.warehouse import (
    RAW_WAREHOUSE_DIRNAME,
    RAW_WAREHOUSE_FILENAME,
    _delete_source_rows,
    _ensure_schema,
    _file_sha256,
    _optional_row_value,
    _upsert_manifest,
    default_raw_warehouse_path,
)
from ai_agents_metrics.storage import ensure_parent_dir

if TYPE_CHECKING:
    from pathlib import Path


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


__all__ = [
    "RAW_WAREHOUSE_DIRNAME",
    "RAW_WAREHOUSE_FILENAME",
    "IngestSummary",
    "default_raw_warehouse_path",
    "ingest_codex_history",
    "render_ingest_summary_json",
    # Private test-facing re-exports: tests/history/test_history_ingest.py
    # and tests/strategies/history.py import these names directly. Keep them
    # reachable from the package root until those tests migrate to
    # submodule imports.
    "_encode_claude_cwd",
    "_ensure_schema",
    "_extract_claude_message_text",
    "_extract_claude_token_usage",
    "_extract_message_text",
    "_extract_token_usage",
    "_import_claude_session_file",
    "_optional_row_value",
]
