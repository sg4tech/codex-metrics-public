"""Usage window resolution: read agent telemetry and compute token/cost summaries."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain import (
    now_utc_datetime,
    parse_iso_datetime,
    parse_iso_datetime_flexible,
    round_usd,
)
from ai_agents_metrics.pricing import (
    THREAD_MODEL_PATTERN,
    compute_claude_event_cost_usd,
    compute_event_cost_usd,
    load_pricing,
    parse_usage_event,
)

if TYPE_CHECKING:
    from ai_agents_metrics.usage_backends import UsageBackend, UsageWindow


def _encode_cwd_for_claude(cwd: Path) -> str:
    """Encode a filesystem path to the directory name used by Claude Code in ~/.claude/projects/.

    Claude Code replaces every '/' and '.' character with '-' when naming the project directory.
    For example: /Users/viktor/.claude/worktrees/foo → -Users-viktor--claude-worktrees-foo
    """
    return str(cwd).replace("/", "-").replace(".", "-")


def _resolve_claude_usage_window_impl(
    claude_root: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    """Parse Claude Code JSONL telemetry to compute token usage and cost for a time window.

    Returns: (cost_usd, total_tokens, input_tokens, cached_input_tokens, output_tokens, model_name)

    token mapping:
      input_tokens           → input_tokens       (plain non-cached input)
      cache_read_input_tokens → cached_input_tokens (cheap cached reads, mapped to existing domain field)
      cache_creation_input_tokens → included in cost and total_tokens (write-to-cache, not a separate domain field)
      output_tokens          → output_tokens
    """
    if started_at is None:
        return None, None, None, None, None, None

    encoded_cwd = _encode_cwd_for_claude(cwd)
    projects_dir = claude_root / "projects" / encoded_cwd
    if not projects_dir.exists():
        return None, None, None, None, None, None

    started_dt = parse_iso_datetime(started_at, "started_at")
    finished_dt = parse_iso_datetime(finished_at, "finished_at") if finished_at is not None else now_utc_datetime()
    if finished_dt < started_dt:
        raise ValueError("finished_at cannot be earlier than started_at")

    pricing = load_pricing(pricing_path)

    # Collect JSONL files: top-level sessions + subagent files
    jsonl_files: list[Path] = list(projects_dir.glob("*.jsonl"))
    for subagent_dir in projects_dir.glob("*/subagents"):
        jsonl_files.extend(subagent_dir.glob("agent-*.jsonl"))

    total_cost = 0.0
    total_input = 0
    total_cache_creation = 0
    total_cache_read = 0
    total_output = 0
    total_tokens = 0
    detected_model: str | None = None
    latest_event_dt = None

    for jsonl_file in jsonl_files:
        try:
            lines = jsonl_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "assistant":
                continue

            ts_str = event.get("timestamp")
            if not ts_str:
                continue
            try:
                event_dt = parse_iso_datetime_flexible(ts_str, "timestamp")
            except ValueError:
                continue

            if not (started_dt <= event_dt <= finished_dt):
                continue

            message = event.get("message") or {}
            usage = message.get("usage") or {}
            model = message.get("model")

            input_toks = int(usage.get("input_tokens") or 0)
            cache_creation_toks = int(usage.get("cache_creation_input_tokens") or 0)
            cache_read_toks = int(usage.get("cache_read_input_tokens") or 0)
            output_toks = int(usage.get("output_tokens") or 0)

            if latest_event_dt is None or event_dt > latest_event_dt:
                latest_event_dt = event_dt
                if model:
                    detected_model = model

            total_input += input_toks
            total_cache_creation += cache_creation_toks
            total_cache_read += cache_read_toks
            total_output += output_toks
            total_tokens += input_toks + cache_creation_toks + cache_read_toks + output_toks

            if model is not None:
                try:
                    total_cost = round_usd(
                        total_cost
                        + compute_claude_event_cost_usd(
                            model=model,
                            input_tokens=input_toks,
                            cache_creation_tokens=cache_creation_toks,
                            cache_read_tokens=cache_read_toks,
                            output_tokens=output_toks,
                            pricing=pricing,
                        )
                    )
                except ValueError:
                    pass  # unknown model — skip cost, still count tokens

    if total_tokens == 0:
        return None, None, None, None, None, None

    return (
        total_cost if total_cost > 0 else None,
        total_tokens,
        total_input,
        total_cache_read,  # mapped to cached_input_tokens in domain
        total_output,
        detected_model,
    )


def resolve_claude_usage_window(
    claude_root: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    """Public entry point for Claude JSONL usage resolution (used by ClaudeUsageBackend)."""
    return _resolve_claude_usage_window_impl(
        claude_root=claude_root,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
        pricing_path=pricing_path,
    )


def find_usage_thread_id(state_path: Path, cwd: Path, thread_id: str | None) -> str | None:
    if not state_path.exists():
        return None

    with sqlite3.connect(state_path) as conn:
        conn.row_factory = sqlite3.Row
        if thread_id is not None:
            row = conn.execute("SELECT id FROM threads WHERE id = ?", (thread_id,)).fetchone()
            return None if row is None else str(row["id"])

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
    return None if row is None else str(row["id"])


def find_codex_thread_id(state_path: Path, cwd: Path, thread_id: str | None) -> str | None:
    return find_usage_thread_id(state_path, cwd, thread_id)


def _resolve_usage_window_impl(
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    if started_at is None or not state_path.exists() or not logs_path.exists():
        return None, None, None, None, None, None

    started_dt = parse_iso_datetime(started_at, "started_at")
    finished_dt = parse_iso_datetime(finished_at, "finished_at") if finished_at is not None else now_utc_datetime()
    if finished_dt < started_dt:
        raise ValueError("finished_at cannot be earlier than started_at")

    resolved_thread_id = find_usage_thread_id(state_path, cwd, thread_id)
    if resolved_thread_id is None:
        return None, None, None, None, None, None

    pricing = load_pricing(pricing_path)
    usage_events: list[dict[str, Any]] = []
    with sqlite3.connect(logs_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT feedback_log_body
            FROM logs
            WHERE feedback_log_body LIKE ?
              AND feedback_log_body LIKE '%event.name="codex.sse_event"%'
              AND feedback_log_body LIKE '%event.kind=response.completed%'
            ORDER BY id ASC
            """,
            (f"%conversation.id={resolved_thread_id}%",),
        ).fetchall()

    for row in rows:
        body = row["feedback_log_body"]
        if body is None:
            continue
        event = parse_usage_event(str(body))
        if event is None:
            continue
        if started_dt <= event["timestamp"] <= finished_dt:
            usage_events.append(event)

    if not usage_events:
        session_cost_usd, session_total_tokens, session_input_tokens, session_cached_input_tokens, session_output_tokens, session_model = resolve_usage_session_window(
            logs_path=logs_path,
            thread_id=resolved_thread_id,
            started_dt=started_dt,
            finished_dt=finished_dt,
            pricing=pricing,
        )
        if (
            session_cost_usd is None
            and session_total_tokens is None
            and session_input_tokens is None
            and session_cached_input_tokens is None
            and session_output_tokens is None
            and session_model is None
        ):
            return None, None, None, None, None, None
        return (
            session_cost_usd,
            session_total_tokens,
            session_input_tokens,
            session_cached_input_tokens,
            session_output_tokens,
            session_model,
        )

    total_cost = 0.0
    total_input_tokens = 0
    total_cached_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    detected_model = None
    for event in usage_events:
        total_cost = round_usd(total_cost + compute_event_cost_usd(event, pricing))
        total_input_tokens += event["input_tokens"]
        total_cached_input_tokens += event["cached_input_tokens"]
        total_output_tokens += event["output_tokens"]
        total_tokens += (
            event["input_tokens"]
            + event["cached_input_tokens"]
            + event["output_tokens"]
            + event["reasoning_tokens"]
            + event["tool_tokens"]
        )
        if detected_model is None and event.get("model") is not None:
            detected_model = event["model"]
    return total_cost, total_tokens, total_input_tokens, total_cached_input_tokens, total_output_tokens, detected_model


class _CodexUsageBackend:
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
        from ai_agents_metrics.usage_backends import UsageWindow  # lazy to avoid cycle
        cost_usd, total_tokens, input_tokens, cached_input_tokens, output_tokens, agent_name = _resolve_usage_window_impl(
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
            model_name=agent_name,
            backend_name=self.name,
        )


DEFAULT_USAGE_BACKEND: UsageBackend = _CodexUsageBackend()


def resolve_usage_window(
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    from ai_agents_metrics.usage_backends import (
        resolve_usage_window as resolve_backend_usage_window,  # lazy to avoid cycle
    )
    from ai_agents_metrics.usage_backends import select_usage_backend  # lazy to avoid cycle
    resolved_backend = select_usage_backend(state_path, cwd, thread_id)
    window = resolve_backend_usage_window(
        resolved_backend,
        state_path=state_path,
        logs_path=logs_path,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
        pricing_path=pricing_path,
        thread_id=thread_id,
    )
    return (
        window.cost_usd,
        window.total_tokens,
        window.input_tokens,
        window.cached_input_tokens,
        window.output_tokens,
        window.model_name,
    )


def resolve_codex_usage_window(
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    from ai_agents_metrics.usage_backends import (
        resolve_usage_window as resolve_backend_usage_window,  # lazy to avoid cycle
    )
    window = resolve_backend_usage_window(
        DEFAULT_USAGE_BACKEND,
        state_path=state_path,
        logs_path=logs_path,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
        pricing_path=pricing_path,
        thread_id=thread_id,
    )
    return (
        window.cost_usd,
        window.total_tokens,
        window.input_tokens,
        window.cached_input_tokens,
        window.output_tokens,
        window.model_name,
    )


def find_session_rollout_path(sessions_root: Path, thread_id: str) -> Path | None:
    if not sessions_root.exists():
        return None

    candidates = sorted(
        sessions_root.rglob(f"*{thread_id}.jsonl"),
        key=lambda path: path.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def resolve_thread_model_from_logs(logs_path: Path, thread_id: str) -> str | None:
    with sqlite3.connect(logs_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT feedback_log_body
            FROM logs
            WHERE thread_id = ?
              AND feedback_log_body LIKE '%model=%'
            ORDER BY id DESC
            LIMIT 200
            """,
            (thread_id,),
        ).fetchall()

    for row in rows:
        body = row["feedback_log_body"]
        if body is None:
            continue
        match = THREAD_MODEL_PATTERN.search(str(body))
        if match is not None:
            return match.group(1)
    return None


def resolve_usage_session_window(
    *,
    logs_path: Path,
    thread_id: str,
    started_dt: datetime,
    finished_dt: datetime,
    pricing: dict[str, dict[str, float | None]],
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    sessions_root = logs_path.parent / "sessions"
    rollout_path = find_session_rollout_path(sessions_root, thread_id)
    if rollout_path is None:
        return None, None, None, None, None, None

    model = resolve_thread_model_from_logs(logs_path, thread_id)
    total_cost = 0.0
    total_input_tokens = 0
    total_cached_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    cost_found = False
    tokens_found = False
    breakdown_found = False
    model_found = model

    with rollout_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("type") != "event_msg":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            timestamp = record.get("timestamp")
            if not isinstance(timestamp, str):
                continue
            event_dt = parse_iso_datetime_flexible(timestamp, "timestamp")
            if not (started_dt <= event_dt <= finished_dt):
                continue

            info = payload.get("info")
            if not isinstance(info, dict):
                continue
            last_usage = info.get("last_token_usage")
            if not isinstance(last_usage, dict):
                continue

            input_tokens = int(last_usage.get("input_tokens", 0))
            cached_input_tokens = int(last_usage.get("cached_input_tokens", 0))
            output_tokens = int(last_usage.get("output_tokens", 0))
            reasoning_tokens = int(last_usage.get("reasoning_output_tokens", 0))
            total_input_tokens += input_tokens
            total_cached_input_tokens += cached_input_tokens
            total_output_tokens += output_tokens
            total_tokens += int(last_usage.get("total_tokens", input_tokens + cached_input_tokens + output_tokens))
            total_tokens += 0
            if reasoning_tokens > 0 and "total_tokens" not in last_usage:
                total_tokens += reasoning_tokens
            tokens_found = True
            breakdown_found = True

            if model is None:
                continue

            event = {
                "model": model,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_input_tokens,
                "output_tokens": output_tokens,
            }
            total_cost = round_usd(total_cost + compute_event_cost_usd(event, pricing))
            cost_found = True

    return (
        round_usd(total_cost) if cost_found else None,
        total_tokens if tokens_found else None,
        total_input_tokens if breakdown_found else None,
        total_cached_input_tokens if breakdown_found else None,
        total_output_tokens if breakdown_found else None,
        model_found if tokens_found else None,
    )


def resolve_codex_session_usage_window(
    *,
    logs_path: Path,
    thread_id: str,
    started_dt: datetime,
    finished_dt: datetime,
    pricing: dict[str, dict[str, float | None]],
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    return resolve_usage_session_window(
        logs_path=logs_path,
        thread_id=thread_id,
        started_dt=started_dt,
        finished_dt=finished_dt,
        pricing=pricing,
    )
