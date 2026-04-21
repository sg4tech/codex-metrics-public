from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from ai_agents_metrics.domain import (
    now_utc_datetime,
    parse_iso_datetime,
    parse_iso_datetime_flexible,
    round_usd,
)

# ---------------------------------------------------------------------------
# Regex patterns for Codex SSE log parsing
# ---------------------------------------------------------------------------

USAGE_FIELD_PATTERNS = {
    "input_tokens": re.compile(r"\binput_token_count=(\d+)"),
    "cached_input_tokens": re.compile(r"\bcached_token_count=(\d+)"),
    "output_tokens": re.compile(r"\boutput_token_count=(\d+)"),
    "reasoning_tokens": re.compile(r"\breasoning_token_count=(\d+)"),
    "tool_tokens": re.compile(r"\btool_token_count=(\d+)"),
    "model": re.compile(r"\bmodel=([^ ]+)"),
    "timestamp": re.compile(r"\bevent\.timestamp=([^ ]+)"),
}
THREAD_MODEL_PATTERN = re.compile(r"\bmodel=([A-Za-z0-9._-]+)")

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def default_pricing_path() -> Path:
    return Path(str(resources.files("ai_agents_metrics").joinpath("data/model_pricing.json")))


PRICING_JSON_PATH = default_pricing_path()


def load_pricing(path: Path) -> dict[str, dict[str, float | None]]:
    if not path.exists():
        raise ValueError(f"Pricing file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    models = data.get("models")
    if not isinstance(models, dict):
        raise ValueError(f"Invalid pricing file format: {path}")

    validated_models: dict[str, dict[str, float | None]] = {}
    for model_name, config in models.items():
        if not isinstance(config, dict):
            raise ValueError(f"Invalid pricing config for model: {model_name}")
        required_fields = ("input_per_million_usd", "cached_input_per_million_usd", "output_per_million_usd")
        optional_fields = ("cache_creation_per_million_usd",)
        validated_config: dict[str, float | None] = {}
        for field_name in required_fields:
            if field_name not in config:
                raise ValueError(f"Missing pricing field {field_name} for model: {model_name}")
            value = config[field_name]
            if value is not None and not isinstance(value, (int, float)):
                raise ValueError(f"Invalid pricing value for {model_name}.{field_name}")
            if isinstance(value, (int, float)) and value < 0:
                raise ValueError(f"Pricing value cannot be negative for {model_name}.{field_name}")
            validated_config[field_name] = None if value is None else float(value)
        for field_name in optional_fields:
            if field_name in config:
                value = config[field_name]
                if value is not None and not isinstance(value, (int, float)):
                    raise ValueError(f"Invalid pricing value for {model_name}.{field_name}")
                if isinstance(value, (int, float)) and value < 0:
                    raise ValueError(f"Pricing value cannot be negative for {model_name}.{field_name}")
                validated_config[field_name] = None if value is None else float(value)
        validated_models[model_name] = validated_config
    return validated_models


def resolve_pricing_model_alias(model: str, pricing: dict[str, dict[str, float | None]]) -> str | None:
    """Resolve a model identifier to its key in the pricing dict, or return None if not found.

    Normalization steps tried in order:
    1. Direct lookup.
    2. Strip trailing date suffix (e.g. claude-sonnet-4-6-20251022 → claude-sonnet-4-6).
    """
    if model in pricing:
        return model

    # Strip trailing date suffix (YYYYMMDD), e.g. claude-sonnet-4-6-20251022 → claude-sonnet-4-6
    date_stripped = re.sub(r"-\d{8}$", "", model)
    if date_stripped != model and date_stripped in pricing:
        return date_stripped

    return None


def resolve_pricing_path(cwd: Path) -> Path:
    """Return the effective pricing file path for the given workspace.

    If a model_pricing.json exists in the workspace root, it overrides the
    bundled default. Otherwise the bundled package file is used.
    """
    workspace_override = cwd / "model_pricing.json"
    if workspace_override.exists():
        return workspace_override
    return default_pricing_path()


def compute_event_cost_usd(event: dict[str, Any], pricing: dict[str, dict[str, float | None]]) -> float:
    pricing_model = resolve_pricing_model_alias(event["model"], pricing)
    if pricing_model is None:
        return 0.0
    model_pricing = pricing[pricing_model]
    cached_rate = model_pricing["cached_input_per_million_usd"]
    if event["cached_input_tokens"] > 0 and cached_rate is None:
        raise ValueError(f"Model {event['model']} does not support cached input pricing")

    input_cost = Decimal(str(model_pricing["input_per_million_usd"])) * Decimal(event["input_tokens"]) / Decimal(1_000_000)
    cached_input_cost = Decimal("0")
    if cached_rate is not None:
        cached_input_cost = Decimal(str(cached_rate)) * Decimal(event["cached_input_tokens"]) / Decimal(1_000_000)
    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(event["output_tokens"]) / Decimal(1_000_000)
    return round_usd(input_cost + cached_input_cost + output_cost)

# ---------------------------------------------------------------------------
# Codex SSE event parsing
# ---------------------------------------------------------------------------


def parse_usage_event(body: str) -> dict[str, Any] | None:
    if 'event.name="codex.sse_event"' not in body or "event.kind=response.completed" not in body:
        return None

    timestamp_match = USAGE_FIELD_PATTERNS["timestamp"].search(body)
    model_match = USAGE_FIELD_PATTERNS["model"].search(body)
    input_match = USAGE_FIELD_PATTERNS["input_tokens"].search(body)
    output_match = USAGE_FIELD_PATTERNS["output_tokens"].search(body)
    cached_match = USAGE_FIELD_PATTERNS["cached_input_tokens"].search(body)
    if timestamp_match is None or model_match is None or input_match is None or output_match is None or cached_match is None:
        return None

    parsed: dict[str, Any] = {
        "timestamp": parse_iso_datetime_flexible(timestamp_match.group(1), "event.timestamp"),
        "model": model_match.group(1),
        "input_tokens": int(input_match.group(1)),
        "cached_input_tokens": int(cached_match.group(1)),
        "output_tokens": int(output_match.group(1)),
    }

    for field_name in ("reasoning_tokens", "tool_tokens"):
        match = USAGE_FIELD_PATTERNS[field_name].search(body)
        parsed[field_name] = int(match.group(1)) if match is not None else 0

    return parsed

# ---------------------------------------------------------------------------
# Claude JSONL resolution
# ---------------------------------------------------------------------------


def _encode_cwd_for_claude(cwd: Path) -> str:
    """Encode a filesystem path to the directory name used by Claude Code in ~/.claude/projects/.

    Claude Code replaces every '/' and '.' character with '-' when naming the project directory.
    For example: /Users/viktor/.claude/worktrees/foo → -Users-viktor--claude-worktrees-foo
    """
    return str(cwd).replace("/", "-").replace(".", "-")


def _compute_claude_event_cost_usd(
    *,
    model: str | None,
    input_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    pricing: dict[str, dict[str, float | None]],
) -> float:
    """Compute cost for a single Claude JSONL assistant event.

    Claude has three distinct token categories:
    - input_tokens: plain (non-cached) input, billed at base input rate
    - cache_creation_input_tokens: tokens written to prompt cache (5-min tier), billed at 1.25× input rate
    - cache_read_input_tokens: tokens read from prompt cache, billed at 0.1× input rate
    - output_tokens: generated output
    """
    if model is None or (input_tokens == 0 and cache_creation_tokens == 0 and cache_read_tokens == 0 and output_tokens == 0):
        return 0.0

    pricing_model = resolve_pricing_model_alias(model, pricing)
    if pricing_model is None:
        return 0.0
    model_pricing = pricing[pricing_model]

    input_cost = Decimal(str(model_pricing["input_per_million_usd"])) * Decimal(input_tokens) / Decimal(1_000_000)

    cache_creation_cost = Decimal("0")
    cache_creation_rate = model_pricing.get("cache_creation_per_million_usd")
    if cache_creation_tokens > 0:
        if cache_creation_rate is None:
            raise ValueError(f"Model {model} does not have cache_creation pricing; cannot price {cache_creation_tokens} cache_creation tokens")
        cache_creation_cost = Decimal(str(cache_creation_rate)) * Decimal(cache_creation_tokens) / Decimal(1_000_000)

    cache_read_cost = Decimal("0")
    cache_read_rate = model_pricing["cached_input_per_million_usd"]
    if cache_read_tokens > 0 and cache_read_rate is not None:
        cache_read_cost = Decimal(str(cache_read_rate)) * Decimal(cache_read_tokens) / Decimal(1_000_000)

    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(output_tokens) / Decimal(1_000_000)

    return round_usd(input_cost + cache_creation_cost + cache_read_cost + output_cost)


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
                        + _compute_claude_event_cost_usd(
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

# ---------------------------------------------------------------------------
# Codex SQLite resolution
# ---------------------------------------------------------------------------


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


def resolve_codex_usage_window(
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    return _resolve_usage_window_impl(
        state_path=state_path,
        logs_path=logs_path,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
        pricing_path=pricing_path,
        thread_id=thread_id,
    )
