#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRICS_JSON_PATH = Path("metrics/codex_metrics.json")
REPORT_MD_PATH = Path("docs/codex-metrics.md")
PRICING_JSON_PATH = Path("pricing/model_pricing.json")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"


ALLOWED_STATUSES = {"in_progress", "success", "fail"}
ALLOWED_FAILURE_REASONS = {
    "unclear_task",
    "missing_context",
    "validation_failed",
    "environment_issue",
    "model_mistake",
    "scope_too_large",
    "tooling_issue",
    "other",
}


@dataclass
class TaskRecord:
    task_id: str
    title: str
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
    cost_usd: float | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None


USAGE_FIELD_PATTERNS = {
    "input_tokens": re.compile(r"\binput_token_count=(\d+)"),
    "cached_input_tokens": re.compile(r"\bcached_token_count=(\d+)"),
    "output_tokens": re.compile(r"\boutput_token_count=(\d+)"),
    "reasoning_tokens": re.compile(r"\breasoning_token_count=(\d+)"),
    "tool_tokens": re.compile(r"\btool_token_count=(\d+)"),
    "model": re.compile(r"\bmodel=([^ ]+)"),
    "timestamp": re.compile(r"\bevent\.timestamp=([^ ]+)"),
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_utc_datetime() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def default_metrics() -> dict[str, Any]:
    return {
        "summary": {
            "closed_tasks": 0,
            "successes": 0,
            "fails": 0,
            "total_attempts": 0,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "success_rate": None,
            "attempts_per_success": None,
            "cost_per_success_usd": None,
            "cost_per_success_tokens": None,
        },
        "tasks": [],
    }


def round_usd(value: Decimal | float) -> float:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(decimal_value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def parse_iso_datetime_flexible(value: str, field_name: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return parse_iso_datetime(normalized, field_name)


def parse_iso_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc

    if parsed.tzinfo is None:
        raise ValueError(f"Invalid {field_name}: timezone offset is required")
    return parsed


def validate_task_record(task: dict[str, Any]) -> None:
    required_fields = {
        "task_id": str,
        "title": str,
        "status": str,
        "attempts": int,
        "started_at": (str, type(None)),
        "finished_at": (str, type(None)),
        "cost_usd": (int, float, type(None)),
        "tokens_total": (int, type(None)),
        "failure_reason": (str, type(None)),
        "notes": (str, type(None)),
    }

    for field_name, allowed_types in required_fields.items():
        if field_name not in task:
            raise ValueError(f"Missing required task field: {field_name}")
        if not isinstance(task[field_name], allowed_types):
            raise ValueError(f"Invalid type for task field: {field_name}")

    if not task["task_id"].strip():
        raise ValueError("task_id cannot be empty")
    if not task["title"].strip():
        raise ValueError("title cannot be empty")

    validate_status(task["status"])
    validate_non_negative_int(task["attempts"], "attempts")

    if task["cost_usd"] is not None:
        validate_non_negative_float(float(task["cost_usd"]), "cost_usd")
    if task["tokens_total"] is not None:
        validate_non_negative_int(task["tokens_total"], "tokens_total")

    validate_failure_reason(task["failure_reason"])
    validate_task_business_rules(task)


def validate_metrics_data(data: dict[str, Any], path: Path) -> None:
    if "summary" not in data or "tasks" not in data:
        raise ValueError(f"Invalid metrics file format: {path}")
    if not isinstance(data["summary"], dict):
        raise ValueError(f"Invalid metrics summary format: {path}")
    if not isinstance(data["tasks"], list):
        raise ValueError(f"Invalid metrics tasks format: {path}")

    task_ids: set[str] = set()
    for task in data["tasks"]:
        if not isinstance(task, dict):
            raise ValueError("Each task record must be an object")
        validate_task_record(task)
        task_id = task["task_id"]
        if task_id in task_ids:
            raise ValueError(f"Duplicate task_id found: {task_id}")
        task_ids.add(task_id)


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


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_metrics()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    validate_metrics_data(data, path)
    return data


def save_metrics(path: Path, data: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def validate_status(status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {status}. Allowed: {sorted(ALLOWED_STATUSES)}")


def validate_failure_reason(reason: str | None) -> None:
    if reason is None:
        return
    if reason not in ALLOWED_FAILURE_REASONS:
        raise ValueError(
            f"Invalid failure reason: {reason}. Allowed: {sorted(ALLOWED_FAILURE_REASONS)}"
        )


def validate_non_negative_int(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def validate_non_negative_float(value: float, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def validate_task_business_rules(task: dict[str, Any]) -> None:
    started_at = task.get("started_at")
    finished_at = task.get("finished_at")
    status = task["status"]
    failure_reason = task.get("failure_reason")

    started_dt = parse_iso_datetime(started_at, "started_at") if started_at is not None else None
    finished_dt = parse_iso_datetime(finished_at, "finished_at") if finished_at is not None else None

    if status == "fail" and failure_reason is None:
        raise ValueError("failure_reason is required when status is fail")
    if status == "success" and failure_reason is not None:
        raise ValueError("failure_reason must be empty when status is success")
    if status == "in_progress" and finished_at is not None:
        raise ValueError("finished_at must be empty when status is in_progress")
    if started_dt is not None and finished_dt is not None and finished_dt < started_dt:
        raise ValueError("finished_at cannot be earlier than started_at")


def get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int | None:
    for idx, task in enumerate(tasks):
        if task.get("task_id") == task_id:
            return idx
    return None


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def format_num(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def format_usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    if "." not in formatted:
        return f"{formatted}.00"
    fractional_part = formatted.split(".", maxsplit=1)[1]
    if len(fractional_part) < 2:
        return formatted + ("0" * (2 - len(fractional_part)))
    return formatted


def recompute_summary(data: dict[str, Any]) -> None:
    tasks: list[dict[str, Any]] = data["tasks"]

    closed_tasks = [t for t in tasks if t["status"] in {"success", "fail"}]
    successes = [t for t in closed_tasks if t["status"] == "success"]
    fails = [t for t in closed_tasks if t["status"] == "fail"]

    total_attempts = sum(int(t.get("attempts") or 0) for t in closed_tasks)

    usd_values = [t["cost_usd"] for t in closed_tasks if t.get("cost_usd") is not None]
    total_cost_usd = float(sum(usd_values)) if usd_values else 0.0

    token_values = [int(t["tokens_total"]) for t in closed_tasks if t.get("tokens_total") is not None]
    total_tokens = sum(token_values) if token_values else 0

    success_rate = (len(successes) / len(closed_tasks)) if closed_tasks else None
    attempts_per_success = (total_attempts / len(successes)) if successes else None

    success_cost_values = [t["cost_usd"] for t in successes if t.get("cost_usd") is not None]
    cost_per_success_usd = (
        float(sum(success_cost_values)) / len(successes)
        if successes and len(success_cost_values) == len(successes)
        else None
    )

    success_token_values = [int(t["tokens_total"]) for t in successes if t.get("tokens_total") is not None]
    cost_per_success_tokens = (
        sum(success_token_values) / len(successes)
        if successes and len(success_token_values) == len(successes)
        else None
    )

    data["summary"] = {
        "closed_tasks": len(closed_tasks),
        "successes": len(successes),
        "fails": len(fails),
        "total_attempts": total_attempts,
        "total_cost_usd": round_usd(total_cost_usd),
        "total_tokens": total_tokens,
        "success_rate": success_rate,
        "attempts_per_success": attempts_per_success,
        "cost_per_success_usd": round_usd(cost_per_success_usd) if cost_per_success_usd is not None else None,
        "cost_per_success_tokens": cost_per_success_tokens,
    }


def generate_report_md(data: dict[str, Any]) -> str:
    summary = data["summary"]
    tasks: list[dict[str, Any]] = data["tasks"]

    lines: list[str] = [
        "# Codex Metrics",
        "",
        "## Current summary",
        "",
        f"- Closed tasks: {summary['closed_tasks']}",
        f"- Successes: {summary['successes']}",
        f"- Fails: {summary['fails']}",
        f"- Total attempts: {summary['total_attempts']}",
        f"- Total cost (USD): {format_usd(summary['total_cost_usd'])}",
        f"- Total tokens: {summary['total_tokens']}",
        f"- Success Rate: {format_pct(summary['success_rate'])}",
        f"- Attempts per Success: {format_num(summary['attempts_per_success'])}",
        f"- Cost per Success (USD): {format_usd(summary['cost_per_success_usd'])}",
        f"- Cost per Success (Tokens): {format_num(summary['cost_per_success_tokens'])}",
        "",
        "## Task log",
        "",
    ]

    if not tasks:
        lines.append("_No tasks recorded yet._")
        lines.append("")
        return "\n".join(lines)

    for task in sorted(tasks, key=lambda x: x.get("started_at") or "", reverse=True):
        lines.extend(
            [
                f"### {task['task_id']} — {task['title']}",
                f"- Status: {task['status']}",
                f"- Attempts: {task['attempts']}",
                f"- Started at: {task['started_at'] or 'n/a'}",
                f"- Finished at: {task['finished_at'] or 'n/a'}",
                f"- Cost (USD): {format_usd(task.get('cost_usd'))}",
                f"- Tokens: {format_num(task.get('tokens_total'))}",
                f"- Failure reason: {task.get('failure_reason') or 'n/a'}",
                f"- Notes: {task.get('notes') or 'n/a'}",
                "",
            ]
        )

    return "\n".join(lines)


def save_report(path: Path, data: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    report = generate_report_md(data)
    path.write_text(report, encoding="utf-8")


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


def upsert_task(
    data: dict[str, Any],
    task_id: str,
    title: str | None,
    status: str | None,
    attempts_delta: int | None,
    attempts_abs: int | None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    failure_reason: str | None,
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
    tasks: list[dict[str, Any]] = data["tasks"]
    task_index = get_task_index(tasks, task_id)

    if task_index is None:
        if title is None:
            raise ValueError("title is required when creating a new task")
        task = TaskRecord(
            task_id=task_id,
            title=title,
            status="in_progress",
            attempts=0,
            started_at=started_at or now_utc_iso(),
            finished_at=None,
            cost_usd=None,
            tokens_total=None,
            failure_reason=None,
            notes=None,
        )
        tasks.append(asdict(task))
        task_index = len(tasks) - 1

    task = tasks[task_index]

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
            started_at=started_at if started_at is not None else task.get("started_at"),
            finished_at=finished_at if finished_at is not None else task.get("finished_at"),
            pricing_path=pricing_path,
            thread_id=codex_thread_id,
        )

    if title is not None:
        if not title.strip():
            raise ValueError("title cannot be empty")
        task["title"] = title
    if status is not None:
        validate_status(status)
        task["status"] = status
    if attempts_abs is not None:
        validate_non_negative_int(attempts_abs, "attempts")
        task["attempts"] = attempts_abs
    if attempts_delta is not None:
        validate_non_negative_int(attempts_delta, "attempts_delta")
        task["attempts"] = int(task.get("attempts") or 0) + attempts_delta

    if cost_usd_set is not None:
        validate_non_negative_float(cost_usd_set, "cost_usd")
        task["cost_usd"] = cost_usd_set
    elif cost_usd_add is not None:
        validate_non_negative_float(cost_usd_add, "cost_usd_add")
        current = task.get("cost_usd") or 0.0
        task["cost_usd"] = round_usd(float(current) + cost_usd_add)
    elif usage_cost_usd is not None:
        current = task.get("cost_usd") or 0.0
        task["cost_usd"] = round_usd(float(current) + usage_cost_usd)
    elif auto_cost_usd is not None:
        task["cost_usd"] = auto_cost_usd

    if tokens_set is not None:
        validate_non_negative_int(tokens_set, "tokens")
        task["tokens_total"] = tokens_set
    elif tokens_add is not None:
        validate_non_negative_int(tokens_add, "tokens_add")
        current = int(task.get("tokens_total") or 0)
        task["tokens_total"] = current + tokens_add
    elif usage_total_tokens is not None:
        current = int(task.get("tokens_total") or 0)
        task["tokens_total"] = current + usage_total_tokens
    elif auto_total_tokens is not None:
        task["tokens_total"] = auto_total_tokens

    if failure_reason is not None:
        validate_failure_reason(failure_reason)
        task["failure_reason"] = failure_reason

    if notes is not None:
        task["notes"] = notes

    if started_at is not None:
        task["started_at"] = started_at

    if finished_at is not None:
        task["finished_at"] = finished_at

    if task["status"] in {"success", "fail"} and not task.get("finished_at"):
        finished_dt = now_utc_datetime()
        started_at_value = task.get("started_at")
        if started_at_value is not None:
            started_dt = parse_iso_datetime(started_at_value, "started_at")
            if finished_dt < started_dt:
                finished_dt = started_dt
        task["finished_at"] = finished_dt.isoformat()
    if task["status"] == "success":
        task["failure_reason"] = None

    validate_task_record(task)

    return task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update Codex task metrics")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize metrics files")
    init_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    init_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing metrics files")

    update_parser = subparsers.add_parser("update", help="Create or update a task")
    update_parser.add_argument("--task-id", required=True)
    update_parser.add_argument("--title")
    update_parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES))
    update_parser.add_argument("--attempts-delta", type=int)
    update_parser.add_argument("--attempts", type=int)
    update_parser.add_argument("--cost-usd-add", type=float)
    update_parser.add_argument("--cost-usd", type=float)
    update_parser.add_argument("--tokens-add", type=int)
    update_parser.add_argument("--tokens", type=int)
    update_parser.add_argument("--model")
    update_parser.add_argument("--input-tokens", type=int)
    update_parser.add_argument("--cached-input-tokens", type=int)
    update_parser.add_argument("--output-tokens", type=int)
    update_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    update_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    update_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    update_parser.add_argument("--codex-thread-id")
    update_parser.add_argument("--failure-reason", choices=sorted(ALLOWED_FAILURE_REASONS))
    update_parser.add_argument("--notes")
    update_parser.add_argument("--started-at")
    update_parser.add_argument("--finished-at")
    update_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    update_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))

    show_parser = subparsers.add_parser("show", help="Print current summary")
    show_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    sync_parser = subparsers.add_parser("sync-codex-usage", help="Backfill usage and cost from local Codex logs")
    sync_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    sync_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    sync_parser.add_argument("--pricing-path", default=str(PRICING_JSON_PATH))
    sync_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    sync_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    sync_parser.add_argument("--codex-thread-id")

    return parser


def print_summary(data: dict[str, Any]) -> None:
    summary = data["summary"]
    print("Codex Metrics Summary")
    print(f"Closed tasks: {summary['closed_tasks']}")
    print(f"Successes: {summary['successes']}")
    print(f"Fails: {summary['fails']}")
    print(f"Total attempts: {summary['total_attempts']}")
    print(f"Total cost (USD): {format_usd(summary['total_cost_usd'])}")
    print(f"Total tokens: {summary['total_tokens']}")
    print(f"Success Rate: {format_pct(summary['success_rate'])}")
    print(f"Attempts per Success: {format_num(summary['attempts_per_success'])}")
    print(f"Cost per Success (USD): {format_usd(summary['cost_per_success_usd'])}")
    print(f"Cost per Success (Tokens): {format_num(summary['cost_per_success_tokens'])}")


def sync_codex_usage(
    data: dict[str, Any],
    cwd: Path,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
) -> int:
    updated_tasks = 0
    tasks: list[dict[str, Any]] = data["tasks"]
    for task in tasks:
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
            validate_task_record(task)
            updated_tasks += 1
    return updated_tasks


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        init_files(metrics_path, report_path, force=args.force)
        print(f"Initialized {metrics_path} and {report_path}")
        return 0

    if args.command == "show":
        metrics_path = Path(args.metrics_path)
        data = load_metrics(metrics_path)
        recompute_summary(data)
        print_summary(data)
        return 0

    if args.command == "sync-codex-usage":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        pricing_path = Path(args.pricing_path)
        codex_state_path = Path(args.codex_state_path)
        codex_logs_path = Path(args.codex_logs_path)
        data = load_metrics(metrics_path)
        updated_tasks = sync_codex_usage(
            data=data,
            cwd=Path.cwd(),
            pricing_path=pricing_path,
            codex_state_path=codex_state_path,
            codex_logs_path=codex_logs_path,
            codex_thread_id=args.codex_thread_id,
        )
        recompute_summary(data)
        save_metrics(metrics_path, data)
        save_report(report_path, data)
        print(f"Synchronized Codex usage for {updated_tasks} task(s)")
        print_summary(data)
        return 0

    if args.command == "update":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        data = load_metrics(metrics_path)
        pricing_path = Path(args.pricing_path)
        codex_state_path = Path(args.codex_state_path)
        codex_logs_path = Path(args.codex_logs_path)

        task = upsert_task(
            data=data,
            task_id=args.task_id,
            title=args.title,
            status=args.status,
            attempts_delta=args.attempts_delta,
            attempts_abs=args.attempts,
            cost_usd_add=args.cost_usd_add,
            cost_usd_set=args.cost_usd,
            tokens_add=args.tokens_add,
            tokens_set=args.tokens,
            failure_reason=args.failure_reason,
            notes=args.notes,
            started_at=args.started_at,
            finished_at=args.finished_at,
            model=args.model,
            input_tokens=args.input_tokens,
            cached_input_tokens=args.cached_input_tokens,
            output_tokens=args.output_tokens,
            pricing_path=pricing_path,
            codex_state_path=codex_state_path,
            codex_logs_path=codex_logs_path,
            codex_thread_id=args.codex_thread_id,
            cwd=Path.cwd(),
        )

        recompute_summary(data)
        save_metrics(metrics_path, data)
        save_report(report_path, data)

        print(f"Updated task {task['task_id']}")
        print(f"Status: {task['status']}")
        print(f"Attempts: {task['attempts']}")
        print_summary(data)
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
