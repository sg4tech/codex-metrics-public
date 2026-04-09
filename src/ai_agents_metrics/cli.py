#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone  # noqa: F401
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from ai_agents_metrics import __version__
from ai_agents_metrics.bootstrap import bootstrap_project as run_bootstrap_project
from ai_agents_metrics.completion import render_completion
from ai_agents_metrics.cost_audit import (
    CostAuditReport,
    render_cost_audit_report_json,  # noqa: F401 — re-exported as cli_module attribute
)
from ai_agents_metrics.domain import (
    ALLOWED_FAILURE_REASONS,
    ALLOWED_RESULT_FITS,
    ALLOWED_STATUSES,
    ALLOWED_TASK_TYPES,
    GoalRecord,
    apply_goal_updates,
    build_merged_notes,
    choose_earliest_timestamp,
    choose_latest_timestamp,
    combine_optional_cost,
    combine_optional_tokens,
    create_goal_record,
    default_metrics,
    finalize_goal_update,
    get_task_index,
    goal_from_dict,
    goal_to_dict,
    load_metrics,
    next_goal_id,
    now_utc_datetime,
    now_utc_iso,
    parse_iso_datetime,
    parse_iso_datetime_flexible,
    recompute_summary,  # noqa: F401 — re-exported as cli_module attribute
    resolve_linked_task_reference,
    round_usd,
    sync_goal_attempt_entries,
    validate_entry_record,
    validate_goal_record,
    validate_goal_supersession_graph,
    validate_non_negative_int,
)
from ai_agents_metrics.git_state import (
    StartedWorkReport,
    detect_started_work,
)
from ai_agents_metrics.git_state import (
    _is_meaningful_worktree_path as _git_state_is_meaningful_worktree_path,
)
from ai_agents_metrics.git_state import (
    _normalize_worktree_path as _git_state_normalize_worktree_path,
)
from ai_agents_metrics.history_audit import (  # noqa: F401 — re-exported as cli_module attributes
    audit_history,
    render_audit_report,
    render_audit_report_json,
)
from ai_agents_metrics.history_compare import (  # noqa: F401 — re-exported as cli_module attributes
    compare_metrics_to_history,
    render_history_compare_report,
    render_history_compare_report_json,
)
from ai_agents_metrics.history_derive import (
    DeriveSummary,
    render_derive_summary_json,  # noqa: F401 — re-exported as cli_module attribute
)
from ai_agents_metrics.history_derive import (
    derive_codex_history as run_derive_codex_history,
)
from ai_agents_metrics.history_ingest import (
    IngestSummary,
    default_raw_warehouse_path,
    render_ingest_summary_json,  # noqa: F401 — re-exported as cli_module attribute
)
from ai_agents_metrics.history_ingest import (
    ingest_codex_history as run_ingest_codex_history,
)
from ai_agents_metrics.history_normalize import (
    NormalizeSummary,
    render_normalize_summary_json,  # noqa: F401 — re-exported as cli_module attribute
)
from ai_agents_metrics.history_normalize import (
    normalize_codex_history as run_normalize_codex_history,
)
from ai_agents_metrics.observability import record_cli_invocation_observation
from ai_agents_metrics.public_boundary import (
    PublicBoundaryReport,
)
from ai_agents_metrics.public_boundary import (
    verify_public_boundary as run_verify_public_boundary,
)
from ai_agents_metrics.reporting import (
    generate_report_md,
    print_summary,  # noqa: F401 — re-exported as cli_module attribute
    render_summary_json,  # noqa: F401 — re-exported as cli_module attribute
)
from ai_agents_metrics.retro_timeline import (  # noqa: F401 — re-exported as cli_module attributes
    derive_retro_timeline,
    render_retro_timeline_report,
    render_retro_timeline_report_json,
)
from ai_agents_metrics.security import (
    SecurityReport,
    render_security_report,
)
from ai_agents_metrics.security import (
    verify_security as run_verify_security,
)
from ai_agents_metrics.storage import (
    atomic_write_text,
    metrics_mutation_lock,  # noqa: F401 — re-exported as cli_module attribute
)
from ai_agents_metrics.usage_backends import (
    ClaudeUsageBackend,
    UsageBackend,
    UsageWindow,
    select_usage_backend,
)
from ai_agents_metrics.usage_backends import (
    resolve_usage_window as resolve_backend_usage_window,
)
from ai_agents_metrics.workflow_fsm import (
    WorkflowEvent,
    WorkflowResolution,
    resolve_workflow_transition,
)

EVENTS_NDJSON_PATH = Path("metrics/events.ndjson")
METRICS_JSON_PATH = EVENTS_NDJSON_PATH  # backward-compat alias used by args.metrics_path
REPORT_MD_PATH = Path("docs/ai-agents-metrics.md")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
CLAUDE_ROOT = Path.home() / ".claude"
RAW_WAREHOUSE_PATH = default_raw_warehouse_path(METRICS_JSON_PATH)
PUBLIC_BOUNDARY_RULES_PATH = Path("config/public-boundary-rules.toml")
SECURITY_RULES_PATH = Path("config/security-rules.toml")
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


def _normalize_worktree_path(path_text: str) -> str:
    return _git_state_normalize_worktree_path(path_text)


def _is_meaningful_worktree_path(path_text: str) -> bool:
    return _git_state_is_meaningful_worktree_path(path_text)


@dataclass(frozen=True)
class ActiveTaskResolution:
    status: str
    goal_id: str | None
    message: str
    started_work_report: StartedWorkReport | None = None


def ingest_codex_history(source_root: Path, warehouse_path: Path) -> IngestSummary:
    return run_ingest_codex_history(source_root=source_root, warehouse_path=warehouse_path)


def normalize_codex_history(warehouse_path: Path) -> NormalizeSummary:
    return run_normalize_codex_history(warehouse_path=warehouse_path)


def derive_codex_history(warehouse_path: Path) -> DeriveSummary:
    return run_derive_codex_history(warehouse_path=warehouse_path)


def verify_public_boundary(*, repo_root: Path, rules_path: Path) -> PublicBoundaryReport:
    return run_verify_public_boundary(repo_root=repo_root, rules_path=rules_path)


def security(*, repo_root: Path, rules_path: Path) -> SecurityReport:
    return run_verify_security(repo_root=repo_root, rules_path=rules_path)


def get_active_goals(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [goal for goal in data["goals"] if goal.get("status") == "in_progress"]


def resolve_workflow_resolution(data: dict[str, Any], cwd: Path, event: WorkflowEvent) -> WorkflowResolution:
    report = detect_started_work(cwd)
    return resolve_workflow_transition(
        active_goal_count=len(get_active_goals(data)),
        started_work_detected=report.started_work_detected if report.git_available else None,
        git_available=report.git_available,
        event=event,
    )


def build_active_task_warning(data: dict[str, Any], cwd: Path) -> str | None:
    resolution = resolve_workflow_resolution(data, cwd, WorkflowEvent.SHOW)
    if resolution.decision.action != "warning":
        return None
    return f"Warning: {resolution.decision.message}."


def ensure_active_task(data: dict[str, Any], cwd: Path) -> ActiveTaskResolution:
    report = detect_started_work(cwd)
    resolution = resolve_workflow_resolution(data, cwd, WorkflowEvent.ENSURE_ACTIVE_TASK)
    decision = resolution.decision
    active_goals = get_active_goals(data)
    if active_goals and decision.action == "no_op":
        active_ids = ", ".join(goal["goal_id"] for goal in active_goals)
        active_goal = active_goals[0]
        return ActiveTaskResolution(
            status="existing",
            goal_id=active_goal["goal_id"] if len(active_goals) == 1 else None,
            message=f"Active goal already exists: {active_ids}",
        )
    if decision.action == "no_op":
        return ActiveTaskResolution(
            status="not_needed",
            goal_id=None,
            message=decision.message,
            started_work_report=report,
        )

    tasks: list[dict[str, Any]] = data["goals"]
    new_task_id = next_goal_id(tasks)
    new_goal = create_goal_record(
        tasks=tasks,
        task_id=new_task_id,
        title="Recover active task for in-progress repository work",
        task_type="meta",
        linked_task_id=None,
        started_at=now_utc_iso(),
        model=None,
    )
    new_goal.notes = (
        "Auto-recovered because repository work was detected before task bookkeeping started. "
        f"Detected changes: {', '.join(report.changed_paths[:5]) if report.changed_paths else 'none'}"
    )
    goal_dict = goal_to_dict(new_goal)
    tasks[-1] = goal_dict
    validate_goal_record(goal_dict)
    return ActiveTaskResolution(
        status="created",
        goal_id=new_task_id,
        message=f"Created recovery goal {new_task_id}",
        started_work_report=report,
    )


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


_CLAUDE_MODEL_ALIASES: dict[str, str] = {
    # Haiku 4.5 alias (without date suffix) → full ID with date
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
}


def resolve_pricing_model_alias(model: str, pricing: dict[str, dict[str, float | None]]) -> str:
    if model in pricing:
        return model

    alias_candidates = [model]

    # Claude model aliases (e.g. claude-haiku-4-5 → claude-haiku-4-5-20251001)
    if model in _CLAUDE_MODEL_ALIASES:
        alias_candidates.append(_CLAUDE_MODEL_ALIASES[model])

    # OpenAI Codex version suffix alias (e.g. gpt-5.4 → gpt-5)
    if model.endswith(".4"):
        alias_candidates.append(model.rsplit(".4", maxsplit=1)[0])
    if model.endswith(".4-mini"):
        alias_candidates.append(model.rsplit(".4-mini", maxsplit=1)[0] + "-mini")

    for candidate in alias_candidates:
        if candidate in pricing:
            return candidate
    raise ValueError(f"Unknown pricing model: {model}")


def compute_event_cost_usd(event: dict[str, Any], pricing: dict[str, dict[str, float | None]]) -> float:
    pricing_model = resolve_pricing_model_alias(event["model"], pricing)
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
CLAUDE_USAGE_BACKEND: UsageBackend = ClaudeUsageBackend()


def resolve_usage_window(
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
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


def resolve_usage_costs(
    pricing_path: Path,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    explicit_cost_fields_used: bool,
    explicit_token_fields_used: bool,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    usage_fields_used = any(value is not None for value in (input_tokens, cached_input_tokens, output_tokens))
    if model is None and not usage_fields_used:
        return None, None, None, None, None, None
    if model is None:
        raise ValueError("model is required when usage token flags are provided")
    if not usage_fields_used:
        raise ValueError("At least one usage token field is required when model is provided")
    if explicit_cost_fields_used or explicit_token_fields_used:
        raise ValueError("model-based usage pricing cannot be combined with explicit cost/token flags")

    input_tokens_value = input_tokens or 0
    cached_input_tokens_value = cached_input_tokens or 0
    output_tokens_value = output_tokens or 0
    validate_non_negative_int(input_tokens_value, "input_tokens")
    validate_non_negative_int(cached_input_tokens_value, "cached_input_tokens")
    validate_non_negative_int(output_tokens_value, "output_tokens")

    pricing = load_pricing(pricing_path)
    pricing_model = resolve_pricing_model_alias(model, pricing)
    model_pricing = pricing[pricing_model]
    cached_rate = model_pricing["cached_input_per_million_usd"]
    if cached_input_tokens_value > 0 and cached_rate is None:
        raise ValueError(f"Model {model} does not support cached input pricing")

    input_cost = Decimal(str(model_pricing["input_per_million_usd"])) * Decimal(input_tokens_value) / Decimal(1_000_000)
    cached_input_cost = Decimal("0")
    if cached_rate is not None:
        cached_input_cost = Decimal(str(cached_rate)) * Decimal(cached_input_tokens_value) / Decimal(1_000_000)
    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(output_tokens_value) / Decimal(1_000_000)
    total_cost = round_usd(input_cost + cached_input_cost + output_cost)
    total_tokens = input_tokens_value + cached_input_tokens_value + output_tokens_value
    return total_cost, total_tokens, input_tokens_value, cached_input_tokens_value, output_tokens_value, model




def save_report(path: Path, data: dict[str, Any]) -> None:
    report = generate_report_md(data)
    atomic_write_text(path, report)


def init_files(metrics_path: Path, report_path: Path | None, force: bool = False) -> None:
    if not force:
        existing_paths = [path for path in (metrics_path, report_path) if path is not None and path.exists()]
        if existing_paths:
            joined_paths = ", ".join(str(path) for path in existing_paths)
            raise ValueError(
                f"Metrics files already exist: {joined_paths}. Use --force to overwrite."
            )
    from ai_agents_metrics.storage import ensure_parent_dir

    ensure_parent_dir(metrics_path)
    metrics_path.write_text("", encoding="utf-8")
    if report_path is not None:
        data = default_metrics()
        recompute_summary(data)
        save_report(report_path, data)


def bootstrap_project(
    *,
    target_dir: Path,
    metrics_path: Path,
    report_path: Path | None,
    policy_path: Path,
    command_path: Path,
    agents_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    result = run_bootstrap_project(
        target_dir=target_dir,
        metrics_path=metrics_path,
        report_path=report_path,
        policy_path=policy_path,
        command_path=command_path,
        agents_path=agents_path,
        force=force,
        dry_run=dry_run,
        load_metrics=load_metrics,
        default_metrics=default_metrics,
        save_report=save_report,
    )
    return result.messages



def resolve_goal_usage_updates(
    *,
    task: GoalRecord,
    usage_backend: UsageBackend | None = None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    claude_root: Path = CLAUDE_ROOT,
) -> tuple[
    float | None,
    int | None,
    int | None,
    int | None,
    int | None,
    str | None,
    float | None,
    int | None,
    int | None,
    int | None,
    int | None,
    str | None,
    str | None,
]:
    explicit_cost_fields_used = cost_usd_add is not None or cost_usd_set is not None
    explicit_token_fields_used = tokens_add is not None or tokens_set is not None

    # Determine effective agent from stored value; detection happens via actual telemetry data below.
    effective_agent_name = task.agent_name
    detected_agent_name: str | None = None

    # Select primary backend.
    # For goals with a stored agent_name, route directly to the correct backend.
    # For goals without a stored agent_name, use the Codex backend (existing detection via SQLite),
    # then fall back to Claude if Codex returns no data (see below).
    if usage_backend is not None:
        resolved_usage_backend: UsageBackend = usage_backend
        usage_state_path = codex_state_path
    elif effective_agent_name == "claude":
        resolved_usage_backend = ClaudeUsageBackend()
        usage_state_path = claude_root
    else:
        resolved_usage_backend = select_usage_backend(codex_state_path, cwd, codex_thread_id)
        usage_state_path = codex_state_path

    usage_cost_usd, usage_total_tokens, usage_input_tokens, usage_cached_input_tokens, usage_output_tokens, usage_model = resolve_usage_costs(
        pricing_path=pricing_path,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        explicit_cost_fields_used=explicit_cost_fields_used,
        explicit_token_fields_used=explicit_token_fields_used,
    )

    auto_cost_usd, auto_total_tokens, auto_input_tokens, auto_cached_input_tokens, auto_output_tokens, auto_model = (
        None,
        None,
        None,
        None,
        None,
        None,
    )
    if usage_cost_usd is None and usage_total_tokens is None:
        task_started_at = task.started_at.isoformat() if task.started_at is not None else None
        task_finished_at = task.finished_at.isoformat() if task.finished_at is not None else None
        window = resolve_backend_usage_window(
            resolved_usage_backend,
            state_path=usage_state_path,
            logs_path=codex_logs_path,
            cwd=cwd,
            started_at=started_at if started_at is not None else task_started_at,
            finished_at=finished_at if finished_at is not None else task_finished_at,
            pricing_path=pricing_path,
            thread_id=codex_thread_id,
        )
        auto_cost_usd = window.cost_usd
        auto_total_tokens = window.total_tokens
        auto_input_tokens = window.input_tokens
        auto_cached_input_tokens = window.cached_input_tokens
        auto_output_tokens = window.output_tokens
        auto_model = window.model_name

        # If the primary backend returned nothing and no agent_name is stored,
        # try Claude as a fallback.  This handles mixed-agent repos correctly:
        # rather than guessing at start time (file-presence heuristic), we let
        # the actual telemetry data decide which agent ran this goal.
        if (
            auto_cost_usd is None
            and auto_total_tokens is None
            and effective_agent_name is None
            and usage_backend is None
        ):
            claude_window = resolve_backend_usage_window(
                ClaudeUsageBackend(),
                state_path=claude_root,
                logs_path=codex_logs_path,
                cwd=cwd,
                started_at=started_at if started_at is not None else task_started_at,
                finished_at=finished_at if finished_at is not None else task_finished_at,
                pricing_path=pricing_path,
                thread_id=None,
            )
            if claude_window.cost_usd is not None or claude_window.total_tokens is not None:
                window = claude_window
                auto_cost_usd = window.cost_usd
                auto_total_tokens = window.total_tokens
                auto_input_tokens = window.input_tokens
                auto_cached_input_tokens = window.cached_input_tokens
                auto_output_tokens = window.output_tokens
                auto_model = window.model_name

        if auto_cost_usd is not None or auto_total_tokens is not None:
            # Write agent_name only when it is a fresh discovery (not already stored).
            if task.agent_name is None:
                detected_agent_name = window.backend_name

    return (
        usage_cost_usd,
        usage_total_tokens,
        usage_input_tokens,
        usage_cached_input_tokens,
        usage_output_tokens,
        usage_model,
        auto_cost_usd,
        auto_total_tokens,
        auto_input_tokens,
        auto_cached_input_tokens,
        auto_output_tokens,
        auto_model,
        detected_agent_name,
    )


def upsert_task(
    data: dict[str, Any],
    task_id: str | None,
    title: str | None,
    task_type: str | None,
    continuation_of: str | None,
    supersedes_task_id: str | None,
    status: str | None,
    attempts_delta: int | None,
    attempts_abs: int | None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    failure_reason: str | None,
    result_fit: str | None,
    notes: str | None,
    started_at: str | None,
    finished_at: str | None,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    claude_root: Path = CLAUDE_ROOT,
    usage_backend: UsageBackend | None = None,
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = data["goals"]
    entries: list[dict[str, Any]] = data["entries"]
    creating_new_task = task_id is None
    if task_id is not None:
        creating_new_task = get_task_index(tasks, task_id) is None
    elif title is None and task_type is None:
        raise ValueError("task_id is required when updating an existing task")
    if task_id is None:
        task_id = next_goal_id(tasks)

    task_index = get_task_index(tasks, task_id)
    linked_task_id = resolve_linked_task_reference(
        tasks=tasks,
        continuation_of=continuation_of,
        supersedes_task_id=supersedes_task_id,
        creating_new_task=creating_new_task,
    )

    if task_index is None:
        create_goal_record(
            tasks=tasks,
            task_id=task_id,
            title=title,
            task_type=task_type,
            linked_task_id=linked_task_id,
            started_at=started_at,
            model=model,
        )
        task_index = len(tasks) - 1

    task = goal_from_dict(tasks[task_index])
    (
        usage_cost_usd,
        usage_total_tokens,
        usage_input_tokens,
        usage_cached_input_tokens,
        usage_output_tokens,
        usage_model,
        auto_cost_usd,
        auto_total_tokens,
        auto_input_tokens,
        auto_cached_input_tokens,
        auto_output_tokens,
        auto_model,
        detected_agent_name,
    ) = (
        resolve_goal_usage_updates(
            task=task,
            usage_backend=usage_backend,
            cost_usd_add=cost_usd_add,
            cost_usd_set=cost_usd_set,
            tokens_add=tokens_add,
            tokens_set=tokens_set,
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            pricing_path=pricing_path,
            codex_state_path=codex_state_path,
            codex_logs_path=codex_logs_path,
            codex_thread_id=codex_thread_id,
            cwd=cwd,
            started_at=started_at,
            finished_at=finished_at,
            claude_root=claude_root,
        )
    )
    apply_goal_updates(
        entries=entries,
        task=task,
        title=title,
        task_type=task_type,
        status=status,
        attempts_delta=attempts_delta,
        attempts_abs=attempts_abs,
        cost_usd_add=cost_usd_add,
        cost_usd_set=cost_usd_set,
        input_tokens_add=None,
        cached_input_tokens_add=None,
        output_tokens_add=None,
        tokens_add=tokens_add,
        tokens_set=tokens_set,
        usage_cost_usd=usage_cost_usd,
        usage_input_tokens=usage_input_tokens,
        usage_cached_input_tokens=usage_cached_input_tokens,
        usage_output_tokens=usage_output_tokens,
        usage_total_tokens=usage_total_tokens,
        auto_cost_usd=auto_cost_usd,
        auto_input_tokens=auto_input_tokens,
        auto_cached_input_tokens=auto_cached_input_tokens,
        auto_output_tokens=auto_output_tokens,
        auto_total_tokens=auto_total_tokens,
        model=model,
        usage_model=usage_model,
        auto_model=auto_model,
        failure_reason=failure_reason,
        notes=notes,
        agent_name=detected_agent_name,
        started_at=started_at,
        finished_at=finished_at,
        result_fit=result_fit,
    )
    finalize_goal_update(task)
    task_dict = goal_to_dict(task)
    tasks[task_index] = task_dict

    return task_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track goal, attempt, failure, and cost metrics for AI-agent-assisted work.",
        epilog=(
            "Examples:\n"
            "  %(prog)s start-task --title \"Add CSV import\" --task-type product\n"
            "  %(prog)s continue-task --task-id 2026-03-29-001 --notes \"Retry after validation failure\"\n"
            "  %(prog)s finish-task --task-id 2026-03-29-001 --status success --notes \"Validated\"\n"
            "  %(prog)s update --title \"Add CSV import\" --task-type product --attempts-delta 1\n"
            "  %(prog)s update --task-id 2026-03-29-001 --status success --notes \"Validated\"\n"
            "  %(prog)s update --task-id 2026-03-29-002 --title \"Retry CSV import\" --task-type product --supersedes-task-id 2026-03-29-001 --status success\n"
            "  %(prog)s ensure-active-task\n"
            "  %(prog)s ingest-codex-history --source-root ~/.codex\n"
            "  %(prog)s normalize-codex-history\n"
            "  %(prog)s derive-codex-history\n"
            "  %(prog)s audit-cost-coverage\n"
            "  %(prog)s sync-usage\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create the metrics JSON source of truth",
        description=(
            "Create the low-level metrics source of truth file. "
            "Use --write-report when you also want a markdown export."
        ),
    )
    init_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    init_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    init_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing metrics files")

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Scaffold ai-agents-metrics into a repository, including an instructions file and policy",
        description=(
            "Create the full ai-agents-metrics repository scaffold: metrics artifact, "
            "docs/ai-agents-metrics-policy.md, and a managed ai-agents-metrics block inside your instructions file. "
            "Use --write-report when you also want the optional markdown export."
        ),
    )
    bootstrap_parser.add_argument("--target-dir", default=".", help="Repository root to initialize")
    bootstrap_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    bootstrap_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    bootstrap_parser.add_argument("--write-report", action="store_true", help="Also create or update the optional markdown report")
    bootstrap_parser.add_argument("--policy-path", default="docs/ai-agents-metrics-policy.md")
    bootstrap_parser.add_argument("--command-path", default="tools/ai-agents-metrics")
    bootstrap_parser.add_argument("--agents-path", "--instructions-path", dest="agents_path", default="AGENTS.md")
    bootstrap_parser.add_argument("--force", action="store_true", help="Replace conflicting scaffold files")
    bootstrap_parser.add_argument("--dry-run", action="store_true", help="Preview planned changes without writing files")

    install_self_parser = subparsers.add_parser(
        "install-self",
        help="Install this executable into ~/bin/ai-agents-metrics",
        description=(
            "Install the current ai-agents-metrics executable into a stable user-local location. "
            "On macOS/Linux this defaults to a symlink at ~/bin/ai-agents-metrics."
        ),
    )
    install_self_parser.add_argument("--target-dir", default=str(Path.home() / "bin"))
    install_self_parser.add_argument("--target-path")
    install_self_parser.add_argument("--command-name", default="ai-agents-metrics")
    install_self_parser.add_argument("--copy", action="store_true", help="Copy the executable instead of creating a symlink")
    install_self_parser.add_argument(
        "--write-shell-profile",
        action="store_true",
        help="Append the target directory to the detected shell profile when it is not already on PATH",
    )

    completion_parser = subparsers.add_parser(
        "completion",
        help="Print shell completion for bash or zsh",
        description=(
            "Print a shell completion script for ai-agents-metrics. "
            "Use this to enable command and option completion in bash or zsh."
        ),
    )
    completion_parser.add_argument("shell", choices=("bash", "zsh"))

    start_parser = subparsers.add_parser(
        "start-task",
        help="Create a new goal and record the first implementation pass",
        description=(
            "Create a new goal with attempts incremented for the first implementation pass. "
            "Use this when starting meaningful work on a new task."
        ),
    )
    start_parser.add_argument("--title", required=True, help="Goal title")
    start_parser.add_argument("--task-type", required=True, choices=sorted(ALLOWED_TASK_TYPES), help="Goal classification")
    start_linked_group = start_parser.add_mutually_exclusive_group()
    start_linked_group.add_argument("--continuation-of", help="Create a new goal linked to a previous closed goal")
    start_linked_group.add_argument("--supersedes-task-id", help="Create a replacement goal for a previous closed goal")
    start_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    start_parser.add_argument("--started-at", help="Explicit ISO8601 start timestamp")
    start_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    start_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    start_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    start_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    start_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    start_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    start_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    start_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    start_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    start_parser.add_argument("--codex-thread-id")
    start_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    start_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    start_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    start_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    continue_parser = subparsers.add_parser(
        "continue-task",
        help="Record another implementation pass for an existing goal",
        description=(
            "Increment attempts for an existing goal and optionally attach notes, failure reason, "
            "or usage data for the new pass."
        ),
    )
    continue_parser.add_argument("--task-id", required=True, help="Existing goal identifier")
    continue_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    continue_parser.add_argument(
        "--failure-reason",
        choices=sorted(ALLOWED_FAILURE_REASONS),
        help="Primary failure reason for the new unsuccessful pass",
    )
    continue_parser.add_argument("--started-at", help="Explicit ISO8601 timestamp for the new pass")
    continue_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    continue_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    continue_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    continue_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    continue_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    continue_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    continue_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    continue_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    continue_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    continue_parser.add_argument("--codex-thread-id")
    continue_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    continue_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    continue_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    continue_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    finish_parser = subparsers.add_parser(
        "finish-task",
        help="Close an existing goal as success or fail",
        description=(
            "Close an existing goal after implementation work is done. Use --status success for a validated "
            "completion or --status fail with a dominant failure reason when the goal did not succeed."
        ),
    )
    finish_parser.add_argument("--task-id", required=True, help="Existing goal identifier")
    finish_parser.add_argument("--status", required=True, choices=("success", "fail"), help="Final goal status")
    finish_parser.add_argument(
        "--failure-reason",
        choices=sorted(ALLOWED_FAILURE_REASONS),
        help="Primary failure reason. Required when closing a goal as fail.",
    )
    finish_parser.add_argument(
        "--result-fit",
        choices=sorted(ALLOWED_RESULT_FITS),
        help="Optional operator quality judgement for closed product goals",
    )
    finish_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    finish_parser.add_argument("--finished-at", help="Explicit ISO8601 finish timestamp")
    finish_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    finish_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    finish_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    finish_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    finish_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    finish_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    finish_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    finish_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    finish_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    finish_parser.add_argument("--codex-thread-id")
    finish_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    finish_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    finish_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    finish_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    update_parser = subparsers.add_parser(
        "update",
        help="Create or update a goal record",
        description=(
            "Create a new goal or update an existing one. For new goals, omit --task-id and let the updater "
            "generate one. Use --attempts-delta for a new implementation pass, --supersedes-task-id for a "
            "replacement goal, and --task-type explicitly for new goals."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s --title \"Improve CLI help\" --task-type product --attempts-delta 1\n"
            "  %(prog)s --task-id 2026-03-29-010 --status success --notes \"Validated\"\n"
            "  %(prog)s --task-id 2026-03-29-011 --title \"Retry CLI help\" --task-type product --supersedes-task-id 2026-03-29-010 --status success\n"
            "  %(prog)s --title \"Write retro\" --task-type retro --attempts-delta 1 --status success\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    update_parser.add_argument(
        "--task-id",
        help=(
            "Stable goal identifier. Omit this for new goals and let the updater generate one. "
            "Pass it when updating an existing goal or replaying history."
        ),
    )
    update_parser.add_argument("--title", help="Goal title. Required for new goals.")
    update_parser.add_argument("--task-type", choices=sorted(ALLOWED_TASK_TYPES), help="Goal classification for new goals")
    linked_task_group = update_parser.add_mutually_exclusive_group()
    linked_task_group.add_argument("--continuation-of", help="Create a new goal linked to a previous closed goal")
    linked_task_group.add_argument("--supersedes-task-id", help="Create a replacement goal for a previous closed goal")
    update_parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES), help="Goal status")
    update_parser.add_argument("--attempts-delta", type=int, help="Increment attempts by this amount")
    update_parser.add_argument("--attempts", type=int, help="Set absolute attempts count")
    update_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    update_parser.add_argument("--cost-usd", type=float, help="Set explicit USD cost")
    update_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    update_parser.add_argument("--tokens", type=int, help="Set explicit token count")
    update_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    update_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    update_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    update_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    update_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    update_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    update_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    update_parser.add_argument("--codex-thread-id")
    update_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    update_parser.add_argument("--failure-reason", choices=sorted(ALLOWED_FAILURE_REASONS), help="Primary failure reason for a failed goal")
    update_parser.add_argument(
        "--result-fit",
        choices=sorted(ALLOWED_RESULT_FITS),
        help="Operator quality judgement for closed product goals: exact_fit, partial_fit, or miss",
    )
    update_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    update_parser.add_argument("--started-at", help="Explicit ISO8601 start timestamp")
    update_parser.add_argument("--finished-at", help="Explicit ISO8601 finish timestamp")
    update_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    update_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    update_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    show_parser = subparsers.add_parser(
        "show",
        help="Print current summary and operator review",
        description="Print the current summary, cost coverage, and operator review.",
    )
    show_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    audit_parser = subparsers.add_parser(
        "audit-history",
        help="Flag suspicious history patterns for manual review",
        description=(
            "Analyze stored goal history and print audit candidates such as likely misses, "
            "partial-fit recoveries, stale in-progress goals, and low-cost-coverage product goals."
        ),
    )
    audit_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    compare_parser = subparsers.add_parser(
        "compare-metrics-history",
        help="Compare the structured metrics ledger against reconstructed Codex history",
        description=(
            "Read the metrics source of truth and a derived Codex history warehouse, then print an "
            "aggregate comparison for the current repository cwd."
        ),
    )
    compare_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    compare_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH))
    compare_parser.add_argument("--cwd", default=str(Path.cwd()))

    ingest_parser = subparsers.add_parser(
        "ingest-codex-history",
        help="Ingest local ~/.codex history into a raw SQLite warehouse",
        description=(
            "Read thread metadata, session transcripts, telemetry events, and logs from a local "
            "Codex history directory into a raw warehouse for later derivation."
        ),
    )
    ingest_parser.add_argument("--source-root", default=str(Path.home() / ".codex"), help="Local Codex history root to read")
    ingest_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path for raw imported data",
    )

    normalize_parser = subparsers.add_parser(
        "normalize-codex-history",
        help="Normalize raw Codex history into analysis-friendly tables",
        description=(
            "Read the raw warehouse populated by ingest-codex-history and build normalized summary tables "
            "for downstream analysis."
        ),
    )
    normalize_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path that already contains raw imported data",
    )

    derive_parser = subparsers.add_parser(
        "derive-codex-history",
        help="Derive analysis marts from normalized Codex history",
        description=(
            "Read the normalized warehouse populated by normalize-codex-history and build reusable "
            "analysis marts for goals, attempts, timelines, retry chains, and session usage."
        ),
    )
    derive_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path that already contains normalized Codex history",
    )

    retro_timeline_parser = subparsers.add_parser(
        "derive-retro-timeline",
        help="Derive before/after product-metric windows around retrospective events",
        description=(
            "Read normalized Codex history from main.normalized_messages, build a retrospective timeline dataset, "
            "write it into the SQLite warehouse, and print before/after product-metric windows around each retro."
        ),
    )
    retro_timeline_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    retro_timeline_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH))
    retro_timeline_parser.add_argument("--cwd", default=str(Path.cwd()))
    retro_timeline_parser.add_argument("--window-size", type=int, default=5)

    cost_audit_parser = subparsers.add_parser(
        "audit-cost-coverage",
        help="Explain why product goals are missing cost coverage",
        description=(
            "Inspect closed product goals and explain why cost coverage is missing, partial, or recoverable."
        ),
    )
    cost_audit_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    cost_audit_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    cost_audit_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    cost_audit_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    cost_audit_parser.add_argument("--codex-thread-id")
    cost_audit_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    public_boundary_parser = subparsers.add_parser(
        "verify-public-boundary",
        help="Verify that a public repository tree does not contain private-only material",
        description=(
            "Check a candidate public repository tree against explicit public-boundary rules. "
            "Fail on forbidden paths, forbidden file types, unexpected roots, or private-content markers."
        ),
    )
    public_boundary_parser.add_argument("--repo-root", default=".")
    public_boundary_parser.add_argument("--rules-path", default=str(PUBLIC_BOUNDARY_RULES_PATH))

    security_parser = subparsers.add_parser(
        "security",
        help="Run a fast staged-file security scan",
        description=(
            "Scan staged changes for secrets, token patterns, private keys, and other dangerous data "
            "before it lands in git."
        ),
    )
    security_parser.add_argument("--repo-root", default=".")
    security_parser.add_argument("--rules-path", default=str(SECURITY_RULES_PATH))

    subparsers.add_parser(
        "ensure-active-task",
        help="Recover or verify active task bookkeeping from local git changes",
        description=(
            "Inspect the current git working tree for meaningful repository work and ensure that active task "
            "bookkeeping exists. If work has started without an active goal, create a recovery draft."
        ),
    ).add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    sync_parser = subparsers.add_parser(
        "sync-usage",
        help="Backfill usage and cost from local agent logs",
        description="Backfill known cost and token totals from local agent telemetry.",
    )
    sync_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    sync_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    sync_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    sync_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    sync_parser.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(CODEX_STATE_PATH))
    sync_parser.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(CODEX_LOGS_PATH))
    sync_parser.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
    sync_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    sync_legacy_parser = subparsers.add_parser(
        "sync-codex-usage",
        help="Deprecated alias for sync-usage",
        description="Backfill known cost and token totals from local agent telemetry.",
    )
    sync_legacy_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    sync_legacy_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    sync_legacy_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    sync_legacy_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    sync_legacy_parser.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(CODEX_STATE_PATH))
    sync_legacy_parser.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(CODEX_LOGS_PATH))
    sync_legacy_parser.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
    sync_legacy_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    merge_parser = subparsers.add_parser(
        "merge-tasks",
        help="Merge a dropped split goal into a kept goal",
        description="Recombine mistakenly split goal history into one kept goal.",
    )
    merge_parser.add_argument("--keep-task-id", required=True, help="Goal that should remain after the merge")
    merge_parser.add_argument("--drop-task-id", required=True, help="Goal that should be merged into the kept goal")
    merge_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    merge_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    merge_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    render_report_parser = subparsers.add_parser(
        "render-report",
        help="Render the optional markdown report from stored metrics",
        description="Generate docs/ai-agents-metrics.md on demand from the JSON source of truth.",
    )
    render_report_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    render_report_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))

    return parser


def sync_usage(
    data: dict[str, Any],
    cwd: Path,
    pricing_path: Path,
    usage_state_path: Path,
    usage_logs_path: Path,
    usage_thread_id: str | None,
    usage_backend: UsageBackend | None = None,
    claude_root: Path = CLAUDE_ROOT,
) -> int:
    updated_tasks = 0
    tasks: list[dict[str, Any]] = data["goals"]
    for task in tasks:
        previous_task = dict(task)
        task_agent_name = task.get("agent_name")
        detected_agent_name: str | None = None
        if usage_backend is not None:
            resolved_backend: UsageBackend = usage_backend
            effective_state_path = usage_state_path
        elif task_agent_name == "claude":
            resolved_backend = ClaudeUsageBackend()
            effective_state_path = claude_root
        else:
            resolved_backend = select_usage_backend(usage_state_path, cwd, usage_thread_id)
            effective_state_path = usage_state_path
        window = resolve_backend_usage_window(
            resolved_backend,
            state_path=effective_state_path,
            logs_path=usage_logs_path,
            cwd=cwd,
            started_at=task.get("started_at"),
            finished_at=task.get("finished_at"),
            pricing_path=pricing_path,
            thread_id=usage_thread_id,
        )
        # If the primary backend returned nothing and no agent_name is stored,
        # try Claude as a fallback (handles mixed-agent repos).
        if (
            window.cost_usd is None
            and window.total_tokens is None
            and task_agent_name is None
            and usage_backend is None
        ):
            claude_window = resolve_backend_usage_window(
                ClaudeUsageBackend(),
                state_path=claude_root,
                logs_path=usage_logs_path,
                cwd=cwd,
                started_at=task.get("started_at"),
                finished_at=task.get("finished_at"),
                pricing_path=pricing_path,
                thread_id=None,
            )
            if claude_window.cost_usd is not None or claude_window.total_tokens is not None:
                window = claude_window
                detected_agent_name = claude_window.backend_name
        auto_cost_usd = window.cost_usd
        auto_total_tokens = window.total_tokens
        auto_input_tokens = window.input_tokens
        auto_cached_input_tokens = window.cached_input_tokens
        auto_output_tokens = window.output_tokens
        auto_model = window.model_name
        if (
            auto_cost_usd is None
            and auto_total_tokens is None
            and auto_input_tokens is None
            and auto_cached_input_tokens is None
            and auto_output_tokens is None
            and auto_model is None
        ):
            continue
        changed = False
        if auto_cost_usd is not None and task.get("cost_usd") != auto_cost_usd:
            task["cost_usd"] = auto_cost_usd
            changed = True
        if auto_input_tokens is not None and task.get("input_tokens") != auto_input_tokens:
            task["input_tokens"] = auto_input_tokens
            changed = True
        if auto_cached_input_tokens is not None and task.get("cached_input_tokens") != auto_cached_input_tokens:
            task["cached_input_tokens"] = auto_cached_input_tokens
            changed = True
        if auto_output_tokens is not None and task.get("output_tokens") != auto_output_tokens:
            task["output_tokens"] = auto_output_tokens
            changed = True
        if auto_total_tokens is not None and task.get("tokens_total") != auto_total_tokens:
            task["tokens_total"] = auto_total_tokens
            changed = True
        if auto_model is not None and task.get("model") != auto_model:
            task["model"] = auto_model
            changed = True
        if detected_agent_name is not None and task.get("agent_name") is None:
            task["agent_name"] = detected_agent_name
            changed = True
        if changed:
            validate_goal_record(task)
            sync_goal_attempt_entries(data, task, previous_task)
            updated_tasks += 1
    return updated_tasks


def sync_codex_usage(
    data: dict[str, Any],
    cwd: Path,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    usage_backend: UsageBackend | None = None,
) -> int:
    return sync_usage(
        data=data,
        cwd=cwd,
        pricing_path=pricing_path,
        usage_state_path=codex_state_path,
        usage_logs_path=codex_logs_path,
        usage_thread_id=codex_thread_id,
        usage_backend=usage_backend,
    )


def audit_cost_coverage(
    data: dict[str, Any],
    *,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    claude_root: Path = CLAUDE_ROOT,
) -> CostAuditReport:
    from ai_agents_metrics.cost_audit import audit_cost_coverage as build_cost_report

    def resolve_cost_audit_usage_window(
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> tuple[float | None, int | None]:
        if agent_name == "claude":
            backend: UsageBackend = ClaudeUsageBackend()
        else:
            backend = select_usage_backend(state_path, cwd, thread_id)
        window = resolve_backend_usage_window(
            backend,
            state_path=state_path,
            logs_path=logs_path,
            cwd=cwd,
            started_at=started_at,
            finished_at=finished_at,
            pricing_path=pricing_path,
            thread_id=thread_id,
        )
        return window.cost_usd, window.total_tokens

    return build_cost_report(
        data,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        claude_root=claude_root,
        cwd=cwd,
        codex_thread_id=codex_thread_id,
        find_thread_id=find_usage_thread_id,
        resolve_usage_window=resolve_cost_audit_usage_window,
    )


def merge_tasks(data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]:
    if keep_task_id == drop_task_id:
        raise ValueError("keep_task_id and drop_task_id must be different")

    tasks: list[dict[str, Any]] = data["goals"]
    keep_index = get_task_index(tasks, keep_task_id)
    drop_index = get_task_index(tasks, drop_task_id)
    if keep_index is None:
        raise ValueError(f"Goal not found: {keep_task_id}")
    if drop_index is None:
        raise ValueError(f"Goal not found: {drop_task_id}")

    kept_task = tasks[keep_index]
    dropped_task = tasks[drop_index]
    if kept_task["status"] not in {"success", "fail"} or dropped_task["status"] not in {"success", "fail"}:
        raise ValueError("only closed goals can be merged")
    if kept_task["goal_type"] != dropped_task["goal_type"]:
        raise ValueError("only goals with the same goal_type can be merged")
    if dropped_task.get("supersedes_goal_id") == keep_task_id:
        raise ValueError("merge would create a supersession cycle")

    simulated_tasks = [dict(task) for task in tasks]
    simulated_kept_task = next(task for task in simulated_tasks if task["goal_id"] == keep_task_id)
    simulated_dropped_task = next(task for task in simulated_tasks if task["goal_id"] == drop_task_id)
    if simulated_kept_task.get("supersedes_goal_id") is None:
        simulated_kept_task["supersedes_goal_id"] = simulated_dropped_task.get("supersedes_goal_id")
    for task in simulated_tasks:
        if task.get("supersedes_goal_id") == drop_task_id:
            task["supersedes_goal_id"] = keep_task_id
    simulated_tasks = [task for task in simulated_tasks if task["goal_id"] != drop_task_id]
    try:
        validate_goal_supersession_graph(simulated_tasks)
    except ValueError as exc:
        raise ValueError("merge would create a supersession cycle") from exc

    kept_task["attempts"] = int(kept_task["attempts"]) + int(dropped_task["attempts"])
    kept_task["started_at"] = choose_earliest_timestamp(kept_task.get("started_at"), dropped_task.get("started_at"))
    kept_task["finished_at"] = choose_latest_timestamp(kept_task.get("finished_at"), dropped_task.get("finished_at"))
    kept_task["cost_usd"] = combine_optional_cost(kept_task.get("cost_usd"), dropped_task.get("cost_usd"))
    kept_task["input_tokens"] = combine_optional_tokens(kept_task.get("input_tokens"), dropped_task.get("input_tokens"))
    kept_task["cached_input_tokens"] = combine_optional_tokens(
        kept_task.get("cached_input_tokens"), dropped_task.get("cached_input_tokens")
    )
    kept_task["output_tokens"] = combine_optional_tokens(kept_task.get("output_tokens"), dropped_task.get("output_tokens"))
    kept_task["tokens_total"] = combine_optional_tokens(kept_task.get("tokens_total"), dropped_task.get("tokens_total"))
    kept_task["notes"] = build_merged_notes(kept_task, dropped_task)
    if kept_task.get("supersedes_goal_id") is None:
        kept_task["supersedes_goal_id"] = dropped_task.get("supersedes_goal_id")
    if kept_task.get("agent_name") is None:
        kept_task["agent_name"] = dropped_task.get("agent_name")

    if kept_task["status"] == "success":
        kept_task["failure_reason"] = None
    elif kept_task.get("failure_reason") is None:
        kept_task["failure_reason"] = dropped_task.get("failure_reason")

    entries: list[dict[str, Any]] = data["entries"]
    for entry in entries:
        if entry.get("goal_id") == drop_task_id:
            entry["goal_id"] = keep_task_id
            validate_entry_record(entry)
    kept_entries = [entry for entry in entries if entry.get("goal_id") == keep_task_id]
    kept_entry_models = [entry.get("model") for entry in kept_entries]
    if kept_entry_models and all(model is not None for model in kept_entry_models):
        distinct_models = {str(model).strip() for model in kept_entry_models if model is not None}
        kept_task["model"] = distinct_models.pop() if len(distinct_models) == 1 else None
    else:
        kept_task["model"] = None
    validate_goal_record(kept_task)
    for task in tasks:
        if task.get("supersedes_goal_id") == drop_task_id:
            task["supersedes_goal_id"] = keep_task_id
            validate_goal_record(task)
    del tasks[drop_index]
    return kept_task


def _record_cli_invocation(args: argparse.Namespace) -> None:
    metrics_path = Path(getattr(args, "metrics_path", METRICS_JSON_PATH))
    command = getattr(args, "command", None)
    if command is None:
        return
    payload: dict[str, Any] = {}
    task_id = getattr(args, "task_id", None)
    if task_id is not None:
        payload["task_id"] = task_id
    keep_task_id = getattr(args, "keep_task_id", None)
    if keep_task_id is not None:
        payload["keep_task_id"] = keep_task_id
    drop_task_id = getattr(args, "drop_task_id", None)
    if drop_task_id is not None:
        payload["drop_task_id"] = drop_task_id
    record_cli_invocation_observation(
        metrics_path,
        command=command,
        cwd=str(Path.cwd()),
        task_id=task_id,
        extra_payload=payload,
    )


def main() -> int:
    from ai_agents_metrics import commands

    parser = build_parser()
    args = parser.parse_args()
    _record_cli_invocation(args)

    if args.command == "init":
        return commands.handle_init(args, sys.modules[__name__])

    if args.command == "show":
        return commands.handle_show(args, sys.modules[__name__])

    if args.command == "bootstrap":
        return commands.handle_bootstrap(args, sys.modules[__name__])

    if args.command == "install-self":
        return commands.handle_install_self(args, sys.modules[__name__])

    if args.command == "completion":
        print(render_completion(build_parser(), args.shell), end="")
        return 0

    if args.command == "start-task":
        return commands.handle_start_task(args, sys.modules[__name__])

    if args.command == "continue-task":
        return commands.handle_continue_task(args, sys.modules[__name__])

    if args.command == "finish-task":
        return commands.handle_finish_task(args, sys.modules[__name__])

    if args.command == "audit-history":
        return commands.handle_audit_history(args, sys.modules[__name__])

    if args.command == "compare-metrics-history":
        return commands.handle_compare_metrics_to_history(args, sys.modules[__name__])

    if args.command == "ingest-codex-history":
        return commands.handle_ingest_codex_history(args, sys.modules[__name__])

    if args.command == "normalize-codex-history":
        return commands.handle_normalize_codex_history(args, sys.modules[__name__])

    if args.command == "derive-codex-history":
        return commands.handle_derive_codex_history(args, sys.modules[__name__])

    if args.command == "derive-retro-timeline":
        return commands.handle_derive_retro_timeline(args, sys.modules[__name__])

    if args.command == "audit-cost-coverage":
        return commands.handle_audit_cost_coverage(args, sys.modules[__name__])

    if args.command == "verify-public-boundary":
        return commands.handle_verify_public_boundary(args, sys.modules[__name__])

    if args.command == "security":
        report = security(
            repo_root=Path(args.repo_root).expanduser(),
            rules_path=Path(args.rules_path).expanduser(),
        )
        print(render_security_report(report))
        return 0 if not report.findings else 1

    if args.command == "ensure-active-task":
        return commands.handle_ensure_active_task(args, sys.modules[__name__])

    if args.command == "sync-usage":
        return commands.handle_sync_usage(args, sys.modules[__name__])

    if args.command == "sync-codex-usage":
        return commands.handle_sync_codex_usage(args, sys.modules[__name__])

    if args.command == "merge-tasks":
        return commands.handle_merge_tasks(args, sys.modules[__name__])

    if args.command == "render-report":
        return commands.handle_render_report(args, sys.modules[__name__])

    if args.command == "update":
        return commands.handle_update(args, sys.modules[__name__])

    parser.error("Unknown command")
    return 2


def console_main() -> int:
    try:
        return main()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(console_main())
