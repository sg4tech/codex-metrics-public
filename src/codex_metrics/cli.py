#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone  # noqa: F401
from decimal import Decimal
from pathlib import Path
from typing import Any

from codex_metrics import domain, reporting, storage
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
PRICING_JSON_PATH = Path(__file__).resolve().parent / "data" / "model_pricing.json"
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
ensure_parent_dir = storage.ensure_parent_dir
atomic_write_text = storage.atomic_write_text
save_metrics = storage.save_metrics
metrics_lock_path = storage.metrics_lock_path
metrics_mutation_lock = storage.metrics_mutation_lock


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


def resolve_codex_usage_window(
    state_path: Path,
    logs_path: Path,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    pricing_path: Path,
    thread_id: str | None = None,
) -> tuple[float | None, int | None]:
    if started_at is None or not state_path.exists() or not logs_path.exists():
        return None, None

    started_dt = parse_iso_datetime(started_at, "started_at")
    finished_dt = parse_iso_datetime(finished_at, "finished_at") if finished_at is not None else now_utc_datetime()
    if finished_dt < started_dt:
        raise ValueError("finished_at cannot be earlier than started_at")

    resolved_thread_id = find_codex_thread_id(state_path, cwd, thread_id)
    if resolved_thread_id is None:
        return None, None

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
        return None, None

    total_cost = 0.0
    total_tokens = 0
    for event in usage_events:
        total_cost = round_usd(total_cost + compute_event_cost_usd(event, pricing))
        total_tokens += (
            event["input_tokens"]
            + event["cached_input_tokens"]
            + event["output_tokens"]
            + event["reasoning_tokens"]
            + event["tool_tokens"]
        )
    return total_cost, total_tokens


def resolve_usage_costs(
    pricing_path: Path,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    explicit_cost_fields_used: bool,
    explicit_token_fields_used: bool,
) -> tuple[float | None, int | None]:
    usage_fields_used = any(value is not None for value in (input_tokens, cached_input_tokens, output_tokens))
    if model is None and not usage_fields_used:
        return None, None
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
    return total_cost, total_tokens




def save_report(path: Path, data: dict[str, Any]) -> None:
    report = generate_report_md(data)
    atomic_write_text(path, report)


def init_files(metrics_path: Path, report_path: Path, force: bool = False) -> None:
    if not force:
        existing_paths = [path for path in (metrics_path, report_path) if path.exists()]
        if existing_paths:
            joined_paths = ", ".join(str(path) for path in existing_paths)
            raise ValueError(
                f"Metrics files already exist: {joined_paths}. Use --force to overwrite."
            )
    data = default_metrics()
    save_metrics(metrics_path, data)
    save_report(report_path, data)


def resolve_goal_usage_updates(
    *,
    task: GoalRecord,
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
) -> tuple[float | None, int | None, float | None, int | None]:
    explicit_cost_fields_used = cost_usd_add is not None or cost_usd_set is not None
    explicit_token_fields_used = tokens_add is not None or tokens_set is not None
    usage_cost_usd, usage_total_tokens = resolve_usage_costs(
        pricing_path=pricing_path,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        explicit_cost_fields_used=explicit_cost_fields_used,
        explicit_token_fields_used=explicit_token_fields_used,
    )

    auto_cost_usd, auto_total_tokens = (None, None)
    if usage_cost_usd is None and usage_total_tokens is None:
        auto_cost_usd, auto_total_tokens = resolve_codex_usage_window(
            state_path=codex_state_path,
            logs_path=codex_logs_path,
            cwd=cwd,
            started_at=started_at if started_at is not None else task.started_at,
            finished_at=finished_at if finished_at is not None else task.finished_at,
            pricing_path=pricing_path,
            thread_id=codex_thread_id,
        )

    return usage_cost_usd, usage_total_tokens, auto_cost_usd, auto_total_tokens


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
        )
        task_index = len(tasks) - 1

    task = goal_from_dict(tasks[task_index])
    usage_cost_usd, usage_total_tokens, auto_cost_usd, auto_total_tokens = (
        resolve_goal_usage_updates(
            task=task,
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
        tokens_add=tokens_add,
        tokens_set=tokens_set,
        usage_cost_usd=usage_cost_usd,
        usage_total_tokens=usage_total_tokens,
        auto_cost_usd=auto_cost_usd,
        auto_total_tokens=auto_total_tokens,
        failure_reason=failure_reason,
        notes=notes,
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
        description="Track goal, attempt, failure, and cost metrics for Codex-driven work.",
        epilog=(
            "Examples:\n"
            "  %(prog)s update --title \"Add CSV import\" --task-type product --attempts-delta 1\n"
            "  %(prog)s update --task-id 2026-03-29-001 --status success --notes \"Validated\"\n"
            "  %(prog)s update --task-id 2026-03-29-002 --title \"Retry CSV import\" --task-type product --supersedes-task-id 2026-03-29-001 --status success\n"
            "  %(prog)s audit-cost-coverage\n"
            "  %(prog)s sync-codex-usage\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize metrics and report files",
        description="Create empty metrics and report files.",
    )
    init_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    init_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing metrics files")

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
        "sync-codex-usage",
        help="Backfill usage and cost from local Codex logs",
        description="Backfill known cost and token totals from local Codex telemetry.",
    )
    sync_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    sync_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    sync_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    sync_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    sync_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    sync_parser.add_argument("--codex-thread-id")

    merge_parser = subparsers.add_parser(
        "merge-tasks",
        help="Merge a dropped split goal into a kept goal",
        description="Recombine mistakenly split goal history into one kept goal.",
    )
    merge_parser.add_argument("--keep-task-id", required=True, help="Goal that should remain after the merge")
    merge_parser.add_argument("--drop-task-id", required=True, help="Goal that should be merged into the kept goal")
    merge_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    merge_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))

    return parser


def sync_codex_usage(
    data: dict[str, Any],
    cwd: Path,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
) -> int:
    updated_tasks = 0
    tasks: list[dict[str, Any]] = data["goals"]
    for task in tasks:
        previous_task = dict(task)
        auto_cost_usd, auto_total_tokens = resolve_codex_usage_window(
            state_path=codex_state_path,
            logs_path=codex_logs_path,
            cwd=cwd,
            started_at=task.get("started_at"),
            finished_at=task.get("finished_at"),
            pricing_path=pricing_path,
            thread_id=codex_thread_id,
        )
        if auto_cost_usd is None and auto_total_tokens is None:
            continue
        changed = False
        if auto_cost_usd is not None and task.get("cost_usd") != auto_cost_usd:
            task["cost_usd"] = auto_cost_usd
            changed = True
        if auto_total_tokens is not None and task.get("tokens_total") != auto_total_tokens:
            task["tokens_total"] = auto_total_tokens
            changed = True
        if changed:
            validate_goal_record(task)
            sync_goal_attempt_entries(data, task, previous_task)
            updated_tasks += 1
    return updated_tasks


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

    return build_cost_report(
        data,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        cwd=cwd,
        codex_thread_id=codex_thread_id,
        find_thread_id=find_codex_thread_id,
        resolve_usage_window=resolve_codex_usage_window,
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
    kept_task["tokens_total"] = combine_optional_tokens(kept_task.get("tokens_total"), dropped_task.get("tokens_total"))
    kept_task["notes"] = build_merged_notes(kept_task, dropped_task)
    if kept_task.get("supersedes_goal_id") is None:
        kept_task["supersedes_goal_id"] = dropped_task.get("supersedes_goal_id")

    if kept_task["status"] == "success":
        kept_task["failure_reason"] = None
    elif kept_task.get("failure_reason") is None:
        kept_task["failure_reason"] = dropped_task.get("failure_reason")

    validate_goal_record(kept_task)
    entries: list[dict[str, Any]] = data["entries"]
    for entry in entries:
        if entry.get("goal_id") == drop_task_id:
            entry["goal_id"] = keep_task_id
            validate_entry_record(entry)
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

    if args.command == "audit-history":
        return commands.handle_audit_history(args, sys.modules[__name__])

    if args.command == "audit-cost-coverage":
        return commands.handle_audit_cost_coverage(args, sys.modules[__name__])

    if args.command == "sync-codex-usage":
        return commands.handle_sync_codex_usage(args, sys.modules[__name__])

    if args.command == "merge-tasks":
        return commands.handle_merge_tasks(args, sys.modules[__name__])

    if args.command == "update":
        return commands.handle_update(args, sys.modules[__name__])

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
