"""Usage-window backends: Codex (SQLite state/logs) and Claude (JSONL telemetry)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai_agents_metrics.usage_resolution import (
    resolve_claude_usage_window,
    resolve_codex_usage_window,
)


@dataclass(frozen=True)
class UsageWindow:
    cost_usd: float | None
    total_tokens: int | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    model_name: str | None
    backend_name: str


class UsageBackend(Protocol):
    name: str

    def resolve_window(
        self,
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
    ) -> UsageWindow: ...


class UnknownUsageBackend:
    name = "unknown"

    # All kwargs are unused: the unknown backend returns an empty window no
    # matter what the caller passes. The signature must match UsageBackend so
    # it can be dispatched through ``resolve_usage_window``.
    def resolve_window(  # pylint: disable=unused-argument
        self,
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
    ) -> UsageWindow:
        return UsageWindow(
            cost_usd=None,
            total_tokens=None,
            input_tokens=None,
            cached_input_tokens=None,
            output_tokens=None,
            model_name=None,
            backend_name=self.name,
        )


UNKNOWN_USAGE_BACKEND: UsageBackend = UnknownUsageBackend()


def detect_usage_backend_name(
    state_path: Path,
    cwd: Path,
    thread_id: str | None,
) -> str | None:
    if not state_path.exists():
        return None

    with sqlite3.connect(state_path) as conn:
        conn.row_factory = sqlite3.Row
        if thread_id is not None:
            try:
                row = conn.execute(
                    "SELECT id, model_provider FROM threads WHERE id = ?",
                    (thread_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                return None
        else:
            try:
                row = conn.execute(
                    """
                    SELECT id, model_provider
                    FROM threads
                    WHERE cwd = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (str(cwd),),
                ).fetchone()
            except sqlite3.OperationalError:
                return None
    if row is None:
        return None

    provider = row["model_provider"] if "model_provider" in row.keys() else None
    if provider in {"anthropic", "claude"}:
        return "claude"
    if provider in {"openai", "codex"}:
        return "codex"
    return None


def detect_backend_name(
    state_path: Path,
    cwd: Path,
    thread_id: str | None,
) -> str | None:
    return detect_usage_backend_name(state_path, cwd, thread_id)


def _select_thread_by_providers(
    conn: sqlite3.Connection,
    cwd: str,
    provider_names: tuple[str, ...],
) -> sqlite3.Row | None:
    placeholders = ",".join("?" for _ in provider_names)
    _prefix = "SELECT id FROM threads WHERE cwd = ? AND model_provider IN ("
    _suffix = ") ORDER BY updated_at DESC LIMIT 1"
    sql = _prefix + placeholders + _suffix  # nosec B608
    return conn.execute(sql, (cwd, *provider_names)).fetchone()


def find_thread_id(
    state_path: Path,
    cwd: Path,
    thread_id: str | None,
    *,
    provider_names: tuple[str, ...] | None = None,
) -> str | None:
    if not state_path.exists():
        return None

    with sqlite3.connect(state_path) as conn:
        conn.row_factory = sqlite3.Row
        if thread_id is not None:
            if provider_names is None:
                row = conn.execute("SELECT id FROM threads WHERE id = ?", (thread_id,)).fetchone()
                return None if row is None else str(row["id"])
            try:
                row = conn.execute("SELECT id, model_provider FROM threads WHERE id = ?", (thread_id,)).fetchone()
            except sqlite3.OperationalError:
                return None
            if row is None:
                return None
            provider_value = row["model_provider"]
            if provider_value in provider_names:
                return str(row["id"])
            return None

        if provider_names is None:
            row = conn.execute(
                """
                SELECT id
                FROM threads
                WHERE cwd = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(cwd),),
            ).fetchone()
        else:
            row = _select_thread_by_providers(conn, str(cwd), provider_names)
    return None if row is None else str(row["id"])


class ClaudeUsageBackend:
    name = "claude"

    # logs_path and thread_id are required by the UsageBackend protocol but
    # unused for Claude (JSONL telemetry is directory-scoped, not SQLite-based).
    # state_path is repurposed as claude_root (e.g. ~/.claude).
    def resolve_window(  # pylint: disable=unused-argument
        self,
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
    ) -> UsageWindow:
        cost_usd, total_tokens, input_tokens, cached_input_tokens, output_tokens, model_name = resolve_claude_usage_window(
            claude_root=state_path,
            cwd=cwd,
            started_at=started_at,
            finished_at=finished_at,
            pricing_path=pricing_path,
        )
        return UsageWindow(
            cost_usd=cost_usd,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            backend_name=self.name,
        )


class CodexUsageBackend:
    name = "codex"

    def resolve_window(
        self,
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
    ) -> UsageWindow:
        cost_usd, total_tokens, input_tokens, cached_input_tokens, output_tokens, model_name = resolve_codex_usage_window(
            state_path=state_path,
            logs_path=logs_path,
            cwd=cwd,
            started_at=started_at,
            finished_at=finished_at,
            pricing_path=pricing_path,
            thread_id=thread_id,
        )
        return UsageWindow(
            cost_usd=cost_usd,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            backend_name=self.name,
        )


USAGE_BACKENDS: dict[str, UsageBackend] = {
    "codex": CodexUsageBackend(),
    "claude": ClaudeUsageBackend(),
    "unknown": UNKNOWN_USAGE_BACKEND,
}


def select_usage_backend(state_path: Path, cwd: Path, thread_id: str | None) -> UsageBackend:
    backend_name = detect_usage_backend_name(state_path, cwd, thread_id)
    if backend_name is None:
        return UNKNOWN_USAGE_BACKEND
    return USAGE_BACKENDS.get(backend_name, UNKNOWN_USAGE_BACKEND)


def resolve_usage_window(
    backend: UsageBackend,
    *,
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> UsageWindow:
    return backend.resolve_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
        pricing_path=pricing_path,
        thread_id=thread_id,
    )
