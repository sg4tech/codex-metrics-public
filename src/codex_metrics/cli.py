#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone  # noqa: F401
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from codex_metrics import __version__, domain, reporting, storage
from codex_metrics.bootstrap import bootstrap_project as run_bootstrap_project
from codex_metrics.completion import render_completion
from codex_metrics.cost_audit import (
    CostAuditReport,
)
from codex_metrics.cost_audit import (
    render_cost_audit_report as render_cost_coverage_audit_report,
)
from codex_metrics.history_audit import (
    audit_history as build_history_audit_report,
)
from codex_metrics.history_audit import (
    render_audit_report as render_history_audit_report,
)
from codex_metrics.usage_backends import (
    ClaudeUsageBackend,
    UsageBackend,
    UsageWindow,
    detect_backend_name,
)
from codex_metrics.usage_backends import (
    resolve_usage_window as resolve_backend_usage_window,
)

build_operator_review = reporting.build_operator_review
audit_history = build_history_audit_report
format_coverage = reporting.format_coverage
format_num = reporting.format_num
format_pct = reporting.format_pct
format_usd = reporting.format_usd
generate_report_md = reporting.generate_report_md
print_summary = reporting.print_summary
render_cost_audit_report = render_cost_coverage_audit_report
render_audit_report = render_history_audit_report

ALLOWED_STATUSES = domain.ALLOWED_STATUSES
ALLOWED_TASK_TYPES = domain.ALLOWED_TASK_TYPES
ALLOWED_FAILURE_REASONS = domain.ALLOWED_FAILURE_REASONS
ALLOWED_RESULT_FITS = domain.ALLOWED_RESULT_FITS
AttemptEntryRecord = domain.AttemptEntryRecord
EffectiveGoalRecord = domain.EffectiveGoalRecord
GoalRecord = domain.GoalRecord
aggregate_chain_costs = domain.aggregate_chain_costs
aggregate_chain_timestamps = domain.aggregate_chain_timestamps
aggregate_chain_tokens = domain.aggregate_chain_tokens
append_missing_attempt_entries = domain.append_missing_attempt_entries
apply_attempt_usage_deltas = domain.apply_attempt_usage_deltas
apply_goal_updates = domain.apply_goal_updates
build_attempt_entry = domain.build_attempt_entry
build_effective_goal_record = domain.build_effective_goal_record
build_effective_goals = domain.build_effective_goals
build_goal_chain = domain.build_goal_chain
build_merged_notes = domain.build_merged_notes
choose_earliest_timestamp = domain.choose_earliest_timestamp
choose_latest_timestamp = domain.choose_latest_timestamp
close_open_attempt_entry = domain.close_open_attempt_entry
close_previous_open_attempt = domain.close_previous_open_attempt
combine_optional_cost = domain.combine_optional_cost
combine_optional_tokens = domain.combine_optional_tokens
compute_entry_summary = domain.compute_entry_summary
compute_numeric_delta = domain.compute_numeric_delta
compute_summary_block = domain.compute_summary_block
create_goal_record = domain.create_goal_record
default_metrics = domain.default_metrics
effective_goal_to_dict = domain.effective_goal_to_dict
empty_summary_block = domain.empty_summary_block
ensure_goal_type_update_allowed = domain.ensure_goal_type_update_allowed
entry_from_dict = domain.entry_from_dict
entry_to_dict = domain.entry_to_dict
finalize_goal_update = domain.finalize_goal_update
get_closed_records = domain.get_closed_records
get_failed_records = domain.get_failed_records
get_goal_entries = domain.get_goal_entries
get_successful_records = domain.get_successful_records
get_task = domain.get_task
get_task_index = domain.get_task_index
goal_from_dict = domain.goal_from_dict
goal_to_dict = domain.goal_to_dict
load_metrics = domain.load_metrics
next_entry_id = domain.next_entry_id
next_goal_id = domain.next_goal_id
normalize_legacy_metrics_data = domain.normalize_legacy_metrics_data
now_utc_datetime = domain.now_utc_datetime
now_utc_iso = domain.now_utc_iso
parse_iso_datetime = domain.parse_iso_datetime
parse_iso_datetime_flexible = domain.parse_iso_datetime_flexible
recompute_summary = domain.recompute_summary
resolve_linked_task_reference = domain.resolve_linked_task_reference
round_usd = domain.round_usd
sum_known_numeric_values = domain.sum_known_numeric_values
sync_goal_attempt_entries = domain.sync_goal_attempt_entries
trim_excess_attempt_entries = domain.trim_excess_attempt_entries
update_latest_attempt_entry = domain.update_latest_attempt_entry
validate_entry_business_rules = domain.validate_entry_business_rules
validate_entry_record = domain.validate_entry_record
validate_failure_reason = domain.validate_failure_reason
validate_goal_entries = domain.validate_goal_entries
validate_goal_record = domain.validate_goal_record
validate_goal_supersession_graph = domain.validate_goal_supersession_graph
validate_metrics_data = domain.validate_metrics_data
validate_non_negative_float = domain.validate_non_negative_float
validate_non_negative_int = domain.validate_non_negative_int
validate_status = domain.validate_status
validate_task_business_rules = domain.validate_task_business_rules
validate_task_type = domain.validate_task_type

METRICS_JSON_PATH = Path("metrics/codex_metrics.json")
REPORT_MD_PATH = Path("docs/codex-metrics.md")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
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
ensure_parent_dir = storage.ensure_parent_dir
atomic_write_text = storage.atomic_write_text
save_metrics = storage.save_metrics
metrics_lock_path = storage.metrics_lock_path
metrics_mutation_lock = storage.metrics_mutation_lock


def default_pricing_path() -> Path:
    return Path(str(resources.files("codex_metrics").joinpath("data/model_pricing.json")))


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


def resolve_pricing_model_alias(model: str, pricing: dict[str, dict[str, float | None]]) -> str:
    if model in pricing:
        return model

    alias_candidates = [model]
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


def find_codex_thread_id(state_path: Path, cwd: Path, thread_id: str | None) -> str | None:
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


def _resolve_codex_usage_window_impl(
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

    resolved_thread_id = find_codex_thread_id(state_path, cwd, thread_id)
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
        session_cost_usd, session_total_tokens, session_input_tokens, session_cached_input_tokens, session_output_tokens, session_model = resolve_codex_session_usage_window(
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
        cost_usd, total_tokens, input_tokens, cached_input_tokens, output_tokens, agent_name = _resolve_codex_usage_window_impl(
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


def select_usage_backend(state_path: Path, cwd: Path, thread_id: str | None) -> UsageBackend:
    backend_name = detect_backend_name(state_path, cwd, thread_id)
    if backend_name == "claude":
        return CLAUDE_USAGE_BACKEND
    return DEFAULT_USAGE_BACKEND


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


def resolve_codex_session_usage_window(
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
    data = default_metrics()
    save_metrics(metrics_path, data)
    if report_path is not None:
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
    resolved_usage_backend = usage_backend or select_usage_backend(codex_state_path, cwd, codex_thread_id)
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
    detected_agent_name = None
    if usage_cost_usd is None and usage_total_tokens is None:
        window = resolve_backend_usage_window(
            resolved_usage_backend,
            state_path=codex_state_path,
            logs_path=codex_logs_path,
            cwd=cwd,
            started_at=started_at if started_at is not None else task.started_at,
            finished_at=finished_at if finished_at is not None else task.finished_at,
            pricing_path=pricing_path,
            thread_id=codex_thread_id,
        )
        auto_cost_usd = window.cost_usd
        auto_total_tokens = window.total_tokens
        auto_input_tokens = window.input_tokens
        auto_cached_input_tokens = window.cached_input_tokens
        auto_output_tokens = window.output_tokens
        auto_model = window.model_name
        if auto_cost_usd is not None or auto_total_tokens is not None:
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
        help="Scaffold codex-metrics into a repository, including an instructions file and policy",
        description=(
            "Create the full codex-metrics repository scaffold: metrics artifact, "
            "docs/codex-metrics-policy.md, and a managed codex-metrics block inside your instructions file. "
            "Use --write-report when you also want the optional markdown export."
        ),
    )
    bootstrap_parser.add_argument("--target-dir", default=".", help="Repository root to initialize")
    bootstrap_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    bootstrap_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    bootstrap_parser.add_argument("--write-report", action="store_true", help="Also create or update the optional markdown report")
    bootstrap_parser.add_argument("--policy-path", default="docs/codex-metrics-policy.md")
    bootstrap_parser.add_argument("--command-path", default="tools/codex-metrics")
    bootstrap_parser.add_argument("--agents-path", "--instructions-path", dest="agents_path", default="AGENTS.md")
    bootstrap_parser.add_argument("--force", action="store_true", help="Replace conflicting scaffold files")
    bootstrap_parser.add_argument("--dry-run", action="store_true", help="Preview planned changes without writing files")

    install_self_parser = subparsers.add_parser(
        "install-self",
        help="Install this executable into ~/bin/codex-metrics",
        description=(
            "Install the current codex-metrics executable into a stable user-local location. "
            "On macOS/Linux this defaults to a symlink at ~/bin/codex-metrics."
        ),
    )
    install_self_parser.add_argument("--target-dir", default=str(Path.home() / "bin"))
    install_self_parser.add_argument("--target-path")
    install_self_parser.add_argument("--command-name", default="codex-metrics")
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
            "Print a shell completion script for codex-metrics. "
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
        description="Generate docs/codex-metrics.md on demand from the JSON source of truth.",
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
) -> int:
    updated_tasks = 0
    tasks: list[dict[str, Any]] = data["goals"]
    for task in tasks:
        previous_task = dict(task)
        resolved_backend = usage_backend or select_usage_backend(usage_state_path, cwd, usage_thread_id)
        window = resolve_backend_usage_window(
            resolved_backend,
            state_path=usage_state_path,
            logs_path=usage_logs_path,
            cwd=cwd,
            started_at=task.get("started_at"),
            finished_at=task.get("finished_at"),
            pricing_path=pricing_path,
            thread_id=usage_thread_id,
        )
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
) -> CostAuditReport:
    from codex_metrics.cost_audit import audit_cost_coverage as build_cost_report

    def resolve_cost_audit_usage_window(
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
    ) -> tuple[float | None, int | None]:
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
        return window.cost_usd, window.total_tokens

    return build_cost_report(
        data,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        cwd=cwd,
        codex_thread_id=codex_thread_id,
        find_thread_id=find_codex_thread_id,
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


def main() -> int:
    from codex_metrics import commands

    parser = build_parser()
    args = parser.parse_args()

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

    if args.command == "audit-cost-coverage":
        return commands.handle_audit_cost_coverage(args, sys.modules[__name__])

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
