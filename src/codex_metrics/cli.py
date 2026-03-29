#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, TypeVar

METRICS_JSON_PATH = Path("metrics/codex_metrics.json")
REPORT_MD_PATH = Path("docs/codex-metrics.md")
PRICING_JSON_PATH = Path(__file__).resolve().parent / "data" / "model_pricing.json"
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
LOCKFILE_SUFFIX = ".lock"


ALLOWED_STATUSES = {"in_progress", "success", "fail"}
ALLOWED_TASK_TYPES = {"product", "retro", "meta"}
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
class GoalRecord:
    goal_id: str
    title: str
    goal_type: str
    supersedes_goal_id: str | None
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
    cost_usd: float | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None


@dataclass
class AttemptEntryRecord:
    entry_id: str
    goal_id: str
    entry_type: str
    inferred: bool
    status: str
    started_at: str | None
    finished_at: str | None
    cost_usd: float | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None


@dataclass
class EffectiveGoalRecord:
    goal_id: str
    title: str
    goal_type: str
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
    cost_usd: float | None
    cost_usd_known: float | None
    cost_complete: bool
    tokens_total: int | None
    tokens_total_known: int | None
    tokens_complete: bool
    failure_reason: str | None
    notes: str | None
    supersedes_goal_id: str | None


StatusRecordT = TypeVar("StatusRecordT", GoalRecord, AttemptEntryRecord, EffectiveGoalRecord)


def goal_from_dict(goal: dict[str, Any]) -> GoalRecord:
    return GoalRecord(
        goal_id=goal["goal_id"],
        title=goal["title"],
        goal_type=goal["goal_type"],
        supersedes_goal_id=goal.get("supersedes_goal_id"),
        status=goal["status"],
        attempts=int(goal["attempts"]),
        started_at=goal.get("started_at"),
        finished_at=goal.get("finished_at"),
        cost_usd=None if goal.get("cost_usd") is None else float(goal["cost_usd"]),
        tokens_total=None if goal.get("tokens_total") is None else int(goal["tokens_total"]),
        failure_reason=goal.get("failure_reason"),
        notes=goal.get("notes"),
    )


def goal_to_dict(goal: GoalRecord) -> dict[str, Any]:
    return asdict(goal)


def entry_from_dict(entry: dict[str, Any]) -> AttemptEntryRecord:
    return AttemptEntryRecord(
        entry_id=entry["entry_id"],
        goal_id=entry["goal_id"],
        entry_type=entry["entry_type"],
        inferred=bool(entry.get("inferred", False)),
        status=entry["status"],
        started_at=entry.get("started_at"),
        finished_at=entry.get("finished_at"),
        cost_usd=None if entry.get("cost_usd") is None else float(entry["cost_usd"]),
        tokens_total=None if entry.get("tokens_total") is None else int(entry["tokens_total"]),
        failure_reason=entry.get("failure_reason"),
        notes=entry.get("notes"),
    )


def entry_to_dict(entry: AttemptEntryRecord) -> dict[str, Any]:
    return asdict(entry)


def effective_goal_to_dict(goal: EffectiveGoalRecord) -> dict[str, Any]:
    return asdict(goal)


LEGACY_GOAL_SUPERSEDES_MAP = {
    "2026-03-29-008": "2026-03-29-007",
}


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
        "summary": empty_summary_block(include_by_task_type=True),
        "goals": [],
        "entries": [],
    }


def empty_summary_block(include_by_task_type: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "closed_tasks": 0,
        "successes": 0,
        "fails": 0,
        "total_attempts": 0,
        "total_cost_usd": 0.0,
        "total_tokens": 0,
        "success_rate": None,
        "attempts_per_closed_task": None,
        "known_cost_successes": 0,
        "known_token_successes": 0,
        "complete_cost_successes": 0,
        "complete_token_successes": 0,
        "known_cost_per_success_usd": None,
        "known_cost_per_success_tokens": None,
        "complete_cost_per_covered_success_usd": None,
        "complete_cost_per_covered_success_tokens": None,
        "cost_per_success_usd": None,
        "cost_per_success_tokens": None,
    }
    if include_by_task_type:
        typed_summary = {
            task_type: empty_summary_block(include_by_task_type=False) for task_type in sorted(ALLOWED_TASK_TYPES)
        }
        summary["by_goal_type"] = typed_summary
        summary["by_task_type"] = typed_summary
        summary["entries"] = {
            "closed_entries": 0,
            "successes": 0,
            "fails": 0,
            "success_rate": None,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "failure_reasons": {},
        }
    return summary


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


def validate_goal_record(goal: dict[str, Any]) -> None:
    required_fields: dict[str, type[Any] | tuple[type[Any], ...]] = {
        "goal_id": str,
        "title": str,
        "goal_type": str,
        "supersedes_goal_id": (str, type(None)),
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
        if field_name not in goal:
            raise ValueError(f"Missing required goal field: {field_name}")
        if not isinstance(goal[field_name], allowed_types):
            raise ValueError(f"Invalid type for goal field: {field_name}")

    goal_record = goal_from_dict(goal)

    if not goal_record.goal_id.strip():
        raise ValueError("goal_id cannot be empty")
    if not goal_record.title.strip():
        raise ValueError("title cannot be empty")

    validate_task_type(goal_record.goal_type)
    validate_status(goal_record.status)
    validate_non_negative_int(goal_record.attempts, "attempts")

    if goal_record.cost_usd is not None:
        validate_non_negative_float(goal_record.cost_usd, "cost_usd")
    if goal_record.tokens_total is not None:
        validate_non_negative_int(goal_record.tokens_total, "tokens_total")

    validate_failure_reason(goal_record.failure_reason)
    validate_task_business_rules(goal)


def validate_entry_record(entry: dict[str, Any]) -> None:
    required_fields: dict[str, type[Any] | tuple[type[Any], ...]] = {
        "entry_id": str,
        "goal_id": str,
        "entry_type": str,
        "status": str,
        "started_at": (str, type(None)),
        "finished_at": (str, type(None)),
        "cost_usd": (int, float, type(None)),
        "tokens_total": (int, type(None)),
        "failure_reason": (str, type(None)),
        "notes": (str, type(None)),
    }

    for field_name, allowed_types in required_fields.items():
        if field_name not in entry:
            raise ValueError(f"Missing required entry field: {field_name}")
        if not isinstance(entry[field_name], allowed_types):
            raise ValueError(f"Invalid type for entry field: {field_name}")

    entry_record = entry_from_dict(entry)

    if not entry_record.entry_id.strip():
        raise ValueError("entry_id cannot be empty")
    if not entry_record.goal_id.strip():
        raise ValueError("goal_id cannot be empty")
    if not entry_record.entry_type.strip():
        raise ValueError("entry_type cannot be empty")

    validate_status(entry_record.status)
    if "inferred" in entry and not isinstance(entry["inferred"], bool):
        raise ValueError("Invalid type for entry field: inferred")
    if entry_record.cost_usd is not None:
        validate_non_negative_float(entry_record.cost_usd, "cost_usd")
    if entry_record.tokens_total is not None:
        validate_non_negative_int(entry_record.tokens_total, "tokens_total")
    validate_failure_reason(entry_record.failure_reason)
    validate_entry_business_rules(entry)


def validate_metrics_data(data: dict[str, Any], path: Path) -> None:
    if "summary" not in data or "goals" not in data or "entries" not in data:
        raise ValueError(f"Invalid metrics file format: {path}")
    if not isinstance(data["summary"], dict):
        raise ValueError(f"Invalid metrics summary format: {path}")
    if not isinstance(data["goals"], list):
        raise ValueError(f"Invalid metrics goals format: {path}")
    if not isinstance(data["entries"], list):
        raise ValueError(f"Invalid metrics entries format: {path}")

    goal_ids: set[str] = set()
    for goal in data["goals"]:
        if not isinstance(goal, dict):
            raise ValueError("Each goal record must be an object")
        validate_goal_record(goal)
        goal_id = goal["goal_id"]
        if goal_id in goal_ids:
            raise ValueError(f"Duplicate goal_id found: {goal_id}")
        goal_ids.add(goal_id)

    for goal in data["goals"]:
        superseded_goal_id = goal.get("supersedes_goal_id")
        if superseded_goal_id is not None and superseded_goal_id not in goal_ids:
            raise ValueError(f"Referenced superseded goal not found: {superseded_goal_id}")

    validate_goal_supersession_graph(data["goals"])

    entry_ids: set[str] = set()
    for entry in data["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("Each entry record must be an object")
        validate_entry_record(entry)
        entry_id = entry["entry_id"]
        if entry_id in entry_ids:
            raise ValueError(f"Duplicate entry_id found: {entry_id}")
        if entry["goal_id"] not in goal_ids:
            raise ValueError(f"Entry references unknown goal_id: {entry['goal_id']}")
        entry_ids.add(entry_id)


def normalize_legacy_metrics_data(data: dict[str, Any]) -> None:
    if "tasks" in data and "goals" not in data:
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            legacy_goals: list[dict[str, Any]] = []
            legacy_entries: list[dict[str, Any]] = []
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                task_type = task.get("task_type", "product")
                supersedes_task_id = task.get("supersedes_task_id")
                task_id = task.get("task_id")
                if task_id in LEGACY_GOAL_SUPERSEDES_MAP and supersedes_task_id is None:
                    supersedes_task_id = LEGACY_GOAL_SUPERSEDES_MAP[task_id]
                goal = {
                    "goal_id": task_id,
                    "title": task.get("title"),
                    "goal_type": task_type,
                    "supersedes_goal_id": supersedes_task_id,
                    "status": task.get("status"),
                    "attempts": task.get("attempts"),
                    "started_at": task.get("started_at"),
                    "finished_at": task.get("finished_at"),
                    "cost_usd": task.get("cost_usd"),
                    "tokens_total": task.get("tokens_total"),
                    "failure_reason": task.get("failure_reason"),
                    "notes": task.get("notes"),
                }
                legacy_goals.append(goal)
                legacy_entries.append(
                    {
                        "entry_id": task_id,
                        "goal_id": task_id,
                        "entry_type": task_type,
                        "status": task.get("status"),
                        "started_at": task.get("started_at"),
                        "finished_at": task.get("finished_at"),
                        "cost_usd": task.get("cost_usd"),
                        "tokens_total": task.get("tokens_total"),
                        "failure_reason": task.get("failure_reason"),
                        "notes": task.get("notes"),
                    }
                )
            data["goals"] = legacy_goals
            data["entries"] = legacy_entries

    goals: Any = data.get("goals")
    if isinstance(goals, list):
        for goal in goals:
            if isinstance(goal, dict) and "goal_type" not in goal:
                goal["goal_type"] = goal.pop("task_type", "product")
            if isinstance(goal, dict) and "goal_id" not in goal:
                goal["goal_id"] = goal.pop("task_id")
            if isinstance(goal, dict) and "supersedes_goal_id" not in goal:
                goal["supersedes_goal_id"] = goal.pop("supersedes_task_id", None)

    entries: Any = data.get("entries")
    if not isinstance(entries, list) and isinstance(goals, list):
        data["entries"] = []
        entries = data["entries"]

    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and "goal_id" not in entry:
                entry["goal_id"] = entry.get("task_id")
            if isinstance(entry, dict) and "entry_id" not in entry:
                entry["entry_id"] = entry.get("goal_id")
            if isinstance(entry, dict) and "entry_type" not in entry:
                entry["entry_type"] = entry.get("task_type", "update")


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
    normalize_legacy_metrics_data(data)
    validate_metrics_data(data, path)
    return data


def atomic_write_text(path: Path, content: str) -> None:
    ensure_parent_dir(path)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp_file:
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)
    tmp_path.replace(path)


def save_metrics(path: Path, data: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    data_to_save = dict(data)
    data_to_save.pop("tasks", None)
    serialized = json.dumps(data_to_save, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, serialized)


def metrics_lock_path(metrics_path: Path) -> Path:
    return metrics_path.with_name(f"{metrics_path.name}{LOCKFILE_SUFFIX}")


@contextlib.contextmanager
def metrics_mutation_lock(metrics_path: Path) -> Any:
    lock_path = metrics_lock_path(metrics_path)
    ensure_parent_dir(lock_path)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        debug_sleep_seconds = float(os.environ.get("CODEX_METRICS_DEBUG_LOCK_HOLD_SECONDS", "0"))
        if debug_sleep_seconds > 0:
            time.sleep(debug_sleep_seconds)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def validate_status(status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {status}. Allowed: {sorted(ALLOWED_STATUSES)}")


def validate_task_type(task_type: str) -> None:
    if task_type not in ALLOWED_TASK_TYPES:
        raise ValueError(f"Invalid task type: {task_type}. Allowed: {sorted(ALLOWED_TASK_TYPES)}")


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
    attempts = task["attempts"]
    failure_reason = task.get("failure_reason")

    started_dt = parse_iso_datetime(started_at, "started_at") if started_at is not None else None
    finished_dt = parse_iso_datetime(finished_at, "finished_at") if finished_at is not None else None

    if status == "fail" and failure_reason is None:
        raise ValueError("failure_reason is required when status is fail")
    if status == "success" and failure_reason is not None:
        raise ValueError("failure_reason must be empty when status is success")
    if status in {"success", "fail"} and attempts == 0:
        raise ValueError("closed goals must have at least one attempt")
    if status == "in_progress" and finished_at is not None:
        raise ValueError("finished_at must be empty when status is in_progress")
    if started_dt is not None and finished_dt is not None and finished_dt < started_dt:
        raise ValueError("finished_at cannot be earlier than started_at")


def validate_entry_business_rules(entry: dict[str, Any]) -> None:
    started_at = entry.get("started_at")
    finished_at = entry.get("finished_at")
    status = entry["status"]
    failure_reason = entry.get("failure_reason")
    inferred = bool(entry.get("inferred", False))

    started_dt = parse_iso_datetime(started_at, "started_at") if started_at is not None else None
    finished_dt = parse_iso_datetime(finished_at, "finished_at") if finished_at is not None else None

    if status == "fail" and failure_reason is None and not inferred:
        raise ValueError("failure_reason is required when status is fail")
    if status == "success" and failure_reason is not None:
        raise ValueError("failure_reason must be empty when status is success")
    if status == "in_progress" and finished_at is not None:
        raise ValueError("finished_at must be empty when status is in_progress")
    if started_dt is not None and finished_dt is not None and finished_dt < started_dt:
        raise ValueError("finished_at cannot be earlier than started_at")


def get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int | None:
    for idx, task in enumerate(tasks):
        if task.get("goal_id") == task_id:
            return idx
    return None


def get_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    task_index = get_task_index(tasks, task_id)
    return None if task_index is None else tasks[task_index]


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


def format_coverage(known_count: int, total_count: int) -> str:
    if total_count == 0:
        return "n/a"
    return f"{known_count}/{total_count}"


def build_operator_review(summary: dict[str, Any]) -> list[str]:
    review: list[str] = []
    product_summary = summary["by_goal_type"]["product"]
    entry_summary = summary["entries"]
    successes = summary["successes"]

    if product_summary["closed_tasks"] == 0:
        review.append("Need more real product goals before trusting workflow conclusions.")
    elif product_summary["closed_tasks"] < 5:
        review.append("Product sample is still small; treat workflow conclusions as provisional.")

    if summary["by_goal_type"]["meta"]["closed_tasks"] > product_summary["closed_tasks"]:
        review.append("Meta work still outweighs product delivery; validate changes on real product goals.")

    if entry_summary["fails"] > 0:
        top_reason = None
        if entry_summary["failure_reasons"]:
            top_reason = max(
                entry_summary["failure_reasons"].items(),
                key=lambda item: item[1],
            )[0]
        if top_reason is None:
            review.append("Retry pressure exists; inspect failed entries and recent attempts.")
        else:
            review.append(f"Retry pressure exists; inspect failed entries, especially {top_reason}.")

    if successes > 0 and summary["known_cost_successes"] < successes:
        review.append("Cost visibility is partial; use known-cost metrics as directional, not final.")

    if summary["complete_cost_successes"] < successes and summary["known_cost_per_success_usd"] is not None:
        review.append("Full cost coverage is still partial; treat complete covered-success averages as strict subset signals.")

    if not review:
        review.append("Signals look stable; continue collecting product-goal history before changing the workflow.")

    return review


def choose_earliest_timestamp(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if parse_iso_datetime(first, "timestamp") <= parse_iso_datetime(second, "timestamp") else second


def choose_latest_timestamp(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if parse_iso_datetime(first, "timestamp") >= parse_iso_datetime(second, "timestamp") else second


def combine_optional_cost(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    return round_usd(first + second)


def combine_optional_tokens(first: int | None, second: int | None) -> int | None:
    if first is None or second is None:
        return None
    return first + second


def build_merged_notes(kept_task: dict[str, Any], dropped_task: dict[str, Any]) -> str:
    notes_parts = [part for part in (kept_task.get("notes"), dropped_task.get("notes")) if part]
    notes_parts.append(
        f"Merged {dropped_task['goal_id']} into {kept_task['goal_id']} to recombine split goal history."
    )
    return " | ".join(notes_parts)


def get_closed_records(records: list[StatusRecordT]) -> list[StatusRecordT]:
    return [record for record in records if record.status in {"success", "fail"}]


def get_successful_records(records: list[StatusRecordT]) -> list[StatusRecordT]:
    return [record for record in records if record.status == "success"]


def get_failed_records(records: list[StatusRecordT]) -> list[StatusRecordT]:
    return [record for record in records if record.status == "fail"]


def sum_known_numeric_values(
    records: list[EffectiveGoalRecord] | list[AttemptEntryRecord],
    field_name: str,
    cast_type: type[int] | type[float],
) -> int | float | None:
    values = [cast_type(value) for record in records if (value := getattr(record, field_name)) is not None]
    if not values:
        return None
    return sum(values)

def build_goal_chain(goal_by_id: dict[str, GoalRecord], terminal_goal: GoalRecord) -> list[GoalRecord]:
    chain: list[GoalRecord] = []
    current_goal = terminal_goal
    visited_goal_ids: set[str] = set()
    while True:
        goal_id = current_goal.goal_id
        if goal_id in visited_goal_ids:
            raise ValueError(f"Detected supersession cycle at goal: {goal_id}")
        visited_goal_ids.add(goal_id)
        chain.append(current_goal)
        previous_goal_id = current_goal.supersedes_goal_id
        if previous_goal_id is None:
            break
        previous_goal = goal_by_id.get(previous_goal_id)
        if previous_goal is None:
            raise ValueError(f"Referenced superseded goal not found: {previous_goal_id}")
        current_goal = previous_goal

    chain.reverse()
    return chain


def aggregate_chain_costs(chain: list[GoalRecord]) -> tuple[float | None, float | None, bool]:
    known_cost_values = [goal.cost_usd for goal in chain if goal.cost_usd is not None]
    aggregated_cost_known = round_usd(sum(known_cost_values)) if known_cost_values else None
    is_complete = len(known_cost_values) == len(chain)
    aggregated_cost = aggregated_cost_known if is_complete else None
    return aggregated_cost, aggregated_cost_known, is_complete


def aggregate_chain_tokens(chain: list[GoalRecord]) -> tuple[int | None, int | None, bool]:
    known_token_values = [goal.tokens_total for goal in chain if goal.tokens_total is not None]
    aggregated_tokens_known = sum(known_token_values) if known_token_values else None
    is_complete = len(known_token_values) == len(chain)
    aggregated_tokens = aggregated_tokens_known if is_complete else None
    return aggregated_tokens, aggregated_tokens_known, is_complete


def aggregate_chain_timestamps(chain: list[GoalRecord]) -> tuple[str | None, str | None]:
    started_at = None
    finished_at = None
    for goal in chain:
        started_at = choose_earliest_timestamp(started_at, goal.started_at)
        finished_at = choose_latest_timestamp(finished_at, goal.finished_at)
    return started_at, finished_at


def build_effective_goal_record(
    terminal_goal: GoalRecord,
    chain: list[GoalRecord],
) -> EffectiveGoalRecord:
    aggregated_cost, aggregated_cost_known, cost_complete = aggregate_chain_costs(chain)
    aggregated_tokens, aggregated_tokens_known, tokens_complete = aggregate_chain_tokens(chain)
    started_at, finished_at = aggregate_chain_timestamps(chain)

    return EffectiveGoalRecord(
        goal_id=terminal_goal.goal_id,
        title=terminal_goal.title,
        goal_type=terminal_goal.goal_type,
        status=terminal_goal.status,
        attempts=sum(goal.attempts for goal in chain),
        started_at=started_at,
        finished_at=finished_at,
        cost_usd=aggregated_cost,
        cost_usd_known=aggregated_cost_known,
        cost_complete=cost_complete,
        tokens_total=aggregated_tokens,
        tokens_total_known=aggregated_tokens_known,
        tokens_complete=tokens_complete,
        failure_reason=terminal_goal.failure_reason,
        notes=terminal_goal.notes,
        supersedes_goal_id=terminal_goal.supersedes_goal_id,
    )


def resolve_linked_task_reference(
    tasks: list[dict[str, Any]],
    continuation_of: str | None,
    supersedes_task_id: str | None,
    creating_new_task: bool,
) -> str | None:
    linked_task_id = continuation_of or supersedes_task_id
    if linked_task_id is None:
        return None
    if not creating_new_task:
        raise ValueError("continuation or supersession links can only be set when creating a new task")

    linked_task = get_task(tasks, linked_task_id)
    if linked_task is None:
        raise ValueError(f"Referenced task not found: {linked_task_id}")
    if linked_task["status"] not in {"success", "fail"}:
        raise ValueError("continuation or supersession must refer to a closed task")
    return linked_task_id


def compute_summary_block(tasks: list[EffectiveGoalRecord]) -> dict[str, Any]:
    closed_tasks = get_closed_records(tasks)
    successes = get_successful_records(closed_tasks)
    fails = get_failed_records(closed_tasks)

    total_attempts = sum(t.attempts for t in closed_tasks)

    total_cost_usd_raw = sum_known_numeric_values(closed_tasks, "cost_usd_known", float)
    total_cost_usd = float(total_cost_usd_raw) if total_cost_usd_raw is not None else 0.0
    total_tokens_raw = sum_known_numeric_values(closed_tasks, "tokens_total_known", int)
    total_tokens = int(total_tokens_raw) if total_tokens_raw is not None else 0

    success_rate = (len(successes) / len(closed_tasks)) if closed_tasks else None
    attempts_per_closed_task = (total_attempts / len(closed_tasks)) if closed_tasks else None

    success_cost_values = [
        t.cost_usd for t in successes if t.cost_complete and t.cost_usd is not None
    ]
    known_success_cost_values = [
        t.cost_usd_known for t in successes if t.cost_usd_known is not None
    ]
    complete_cost_per_covered_success_usd = (
        float(sum(success_cost_values)) / len(success_cost_values)
        if success_cost_values
        else None
    )
    cost_per_success_usd = (
        float(sum(success_cost_values)) / len(successes)
        if successes and len(success_cost_values) == len(successes)
        else None
    )
    known_cost_per_success_usd = (
        float(sum(known_success_cost_values)) / len(known_success_cost_values)
        if known_success_cost_values
        else None
    )

    success_token_values = [
        t.tokens_total
        for t in successes
        if t.tokens_complete and t.tokens_total is not None
    ]
    known_success_token_values = [
        t.tokens_total_known
        for t in successes
        if t.tokens_total_known is not None
    ]
    complete_cost_per_covered_success_tokens = (
        sum(success_token_values) / len(success_token_values)
        if success_token_values
        else None
    )
    cost_per_success_tokens = (
        sum(success_token_values) / len(successes)
        if successes and len(success_token_values) == len(successes)
        else None
    )
    known_cost_per_success_tokens = (
        sum(known_success_token_values) / len(known_success_token_values)
        if known_success_token_values
        else None
    )

    return {
        "closed_tasks": len(closed_tasks),
        "successes": len(successes),
        "fails": len(fails),
        "total_attempts": total_attempts,
        "total_cost_usd": round_usd(total_cost_usd),
        "total_tokens": total_tokens,
        "success_rate": success_rate,
        "attempts_per_closed_task": attempts_per_closed_task,
        "known_cost_successes": len(known_success_cost_values),
        "known_token_successes": len(known_success_token_values),
        "complete_cost_successes": len(success_cost_values),
        "complete_token_successes": len(success_token_values),
        "known_cost_per_success_usd": round_usd(known_cost_per_success_usd)
        if known_cost_per_success_usd is not None
        else None,
        "known_cost_per_success_tokens": known_cost_per_success_tokens,
        "complete_cost_per_covered_success_usd": round_usd(complete_cost_per_covered_success_usd)
        if complete_cost_per_covered_success_usd is not None
        else None,
        "complete_cost_per_covered_success_tokens": complete_cost_per_covered_success_tokens,
        "cost_per_success_usd": round_usd(cost_per_success_usd) if cost_per_success_usd is not None else None,
        "cost_per_success_tokens": cost_per_success_tokens,
    }


def build_effective_goals(goals: list[GoalRecord]) -> list[EffectiveGoalRecord]:
    goal_by_id = {goal.goal_id: goal for goal in goals}
    superseded_goal_ids = {
        goal.supersedes_goal_id
        for goal in goals
        if goal.supersedes_goal_id is not None
    }
    effective_goals: list[EffectiveGoalRecord] = []

    for terminal_goal in goals:
        if terminal_goal.goal_id in superseded_goal_ids:
            continue

        chain = build_goal_chain(goal_by_id, terminal_goal)
        effective_goals.append(build_effective_goal_record(terminal_goal, chain))

    return effective_goals


def validate_goal_supersession_graph(goals: list[dict[str, Any]]) -> None:
    goal_records = [goal_from_dict(goal) for goal in goals]
    goal_by_id = {goal.goal_id: goal for goal in goal_records}
    for goal in goal_records:
        build_goal_chain(goal_by_id, goal)


def compute_entry_summary(entries: list[AttemptEntryRecord]) -> dict[str, Any]:
    closed_entries = get_closed_records(entries)
    successes = get_successful_records(closed_entries)
    fails = get_failed_records(closed_entries)
    total_cost_usd_raw = sum_known_numeric_values(closed_entries, "cost_usd", float)
    total_tokens_raw = sum_known_numeric_values(closed_entries, "tokens_total", int)
    failure_reason_counts: dict[str, int] = {}
    for entry in fails:
        if entry.inferred:
            continue
        reason = entry.failure_reason or "other"
        failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1

    return {
        "closed_entries": len(closed_entries),
        "successes": len(successes),
        "fails": len(fails),
        "success_rate": (len(successes) / len(closed_entries)) if closed_entries else None,
        "total_cost_usd": round_usd(float(total_cost_usd_raw)) if total_cost_usd_raw is not None else 0.0,
        "total_tokens": int(total_tokens_raw) if total_tokens_raw is not None else 0,
        "failure_reasons": dict(sorted(failure_reason_counts.items())),
    }


def recompute_summary(data: dict[str, Any]) -> None:
    goals: list[dict[str, Any]] = data["goals"]
    entries: list[dict[str, Any]] = data["entries"]
    goal_records = [goal_from_dict(goal) for goal in goals]
    entry_records = [entry_from_dict(entry) for entry in entries]
    effective_goal_records = build_effective_goals(goal_records)
    summary = compute_summary_block(effective_goal_records)
    by_goal_type = {
        task_type: compute_summary_block([goal for goal in effective_goal_records if goal.goal_type == task_type])
        for task_type in sorted(ALLOWED_TASK_TYPES)
    }
    summary["by_goal_type"] = by_goal_type
    summary["by_task_type"] = by_goal_type
    summary["entries"] = compute_entry_summary(entry_records)
    data["summary"] = summary


def generate_report_md(data: dict[str, Any]) -> str:
    summary = data["summary"]
    goals: list[dict[str, Any]] = data["goals"]
    entries: list[dict[str, Any]] = data["entries"]
    operator_review = build_operator_review(summary)

    lines: list[str] = [
        "# Codex Metrics",
        "",
        "## Goal summary",
        "",
        f"- Closed goals: {summary['closed_tasks']}",
        f"- Successes: {summary['successes']}",
        f"- Fails: {summary['fails']}",
        f"- Total attempts: {summary['total_attempts']}",
        f"- Known total cost (USD): {format_usd(summary['total_cost_usd'])}",
        f"- Known total tokens: {summary['total_tokens']}",
        f"- Success Rate: {format_pct(summary['success_rate'])}",
        f"- Attempts per Closed Goal: {format_num(summary['attempts_per_closed_task'])}",
        f"- Known cost coverage: {format_coverage(summary['known_cost_successes'], summary['successes'])} successful goals",
        f"- Known token coverage: {format_coverage(summary['known_token_successes'], summary['successes'])} successful goals",
        f"- Complete cost coverage: {format_coverage(summary['complete_cost_successes'], summary['successes'])} successful goals",
        f"- Complete token coverage: {format_coverage(summary['complete_token_successes'], summary['successes'])} successful goals",
        f"- Known Cost per Success (USD): {format_usd(summary['known_cost_per_success_usd'])}",
        f"- Known Cost per Success (Tokens): {format_num(summary['known_cost_per_success_tokens'])}",
        f"- Complete Cost per Covered Success (USD): {format_usd(summary['complete_cost_per_covered_success_usd'])}",
        f"- Complete Cost per Covered Success (Tokens): {format_num(summary['complete_cost_per_covered_success_tokens'])}",
        "",
        "## Entry summary",
        "",
        f"- Closed entries: {summary['entries']['closed_entries']}",
        f"- Successes: {summary['entries']['successes']}",
        f"- Fails: {summary['entries']['fails']}",
        f"- Success Rate: {format_pct(summary['entries']['success_rate'])}",
        f"- Known total cost (USD): {format_usd(summary['entries']['total_cost_usd'])}",
        f"- Known total tokens: {summary['entries']['total_tokens']}",
        "",
        "## Operator review",
        "",
    ]
    lines.extend(f"- {line}" for line in operator_review)
    lines.extend(
        [
            "",
            "## By goal type",
            "",
        ]
    )

    failure_reasons = summary["entries"]["failure_reasons"]
    if failure_reasons:
        lines.extend(
            [
                "### Entry failure reasons",
            ]
        )
        for reason, count in failure_reasons.items():
            lines.append(f"- {reason}: {count}")
        lines.append("")

    for task_type in ("product", "retro", "meta"):
        type_summary = summary["by_goal_type"][task_type]
        lines.extend(
            [
                f"### {task_type}",
                f"- Closed goals: {type_summary['closed_tasks']}",
                f"- Successes: {type_summary['successes']}",
                f"- Fails: {type_summary['fails']}",
                f"- Total attempts: {type_summary['total_attempts']}",
                f"- Known total cost (USD): {format_usd(type_summary['total_cost_usd'])}",
                f"- Known total tokens: {type_summary['total_tokens']}",
                f"- Success Rate: {format_pct(type_summary['success_rate'])}",
                f"- Attempts per Closed Goal: {format_num(type_summary['attempts_per_closed_task'])}",
                f"- Known cost coverage: {format_coverage(type_summary['known_cost_successes'], type_summary['successes'])} successful goals",
                f"- Known token coverage: {format_coverage(type_summary['known_token_successes'], type_summary['successes'])} successful goals",
                f"- Complete cost coverage: {format_coverage(type_summary['complete_cost_successes'], type_summary['successes'])} successful goals",
                f"- Complete token coverage: {format_coverage(type_summary['complete_token_successes'], type_summary['successes'])} successful goals",
                f"- Known Cost per Success (USD): {format_usd(type_summary['known_cost_per_success_usd'])}",
                f"- Known Cost per Success (Tokens): {format_num(type_summary['known_cost_per_success_tokens'])}",
                f"- Complete Cost per Covered Success (USD): {format_usd(type_summary['complete_cost_per_covered_success_usd'])}",
                f"- Complete Cost per Covered Success (Tokens): {format_num(type_summary['complete_cost_per_covered_success_tokens'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## Goal log",
            "",
        ]
    )

    if not goals:
        lines.append("_No goals recorded yet._")
        lines.append("")
        return "\n".join(lines)

    for task in sorted(goals, key=lambda x: x.get("started_at") or "", reverse=True):
        lines.extend(
            [
                f"### {task['goal_id']} — {task['title']}",
                f"- Goal type: {task['goal_type']}",
                f"- Supersedes goal: {task.get('supersedes_goal_id') or 'n/a'}",
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

    lines.extend(
        [
            "## Entry log",
            "",
        ]
    )
    for entry in sorted(entries, key=lambda x: x.get("started_at") or "", reverse=True):
        lines.extend(
            [
                f"### {entry['entry_id']} — {entry['goal_id']}",
                f"- Entry type: {entry['entry_type']}",
                f"- Inferred: {'yes' if entry.get('inferred') else 'no'}",
                f"- Status: {entry['status']}",
                f"- Started at: {entry['started_at'] or 'n/a'}",
                f"- Finished at: {entry['finished_at'] or 'n/a'}",
                f"- Cost (USD): {format_usd(entry.get('cost_usd'))}",
                f"- Tokens: {format_num(entry.get('tokens_total'))}",
                f"- Failure reason: {entry.get('failure_reason') or 'n/a'}",
                f"- Notes: {entry.get('notes') or 'n/a'}",
                "",
            ]
        )

    return "\n".join(lines)


def save_report(path: Path, data: dict[str, Any]) -> None:
    report = generate_report_md(data)
    atomic_write_text(path, report)


def get_goal_entries(entries: list[dict[str, Any]], goal_id: str) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry.get("goal_id") == goal_id]


def ensure_goal_type_update_allowed(
    entries: list[dict[str, Any]],
    goal: GoalRecord,
    new_goal_type: str | None,
) -> None:
    if new_goal_type is None or new_goal_type == goal.goal_type:
        return
    if get_goal_entries(entries, goal.goal_id):
        raise ValueError(
            f"goal_id already exists as a {goal.goal_type} goal; "
            "use a new --task-id or omit it for auto-generation to create a new goal"
        )


def next_entry_id(entries: list[dict[str, Any]], goal_id: str) -> str:
    existing_ids = {entry["entry_id"] for entry in entries}
    entry_number = 1
    while True:
        candidate = f"{goal_id}-attempt-{entry_number:03d}"
        if candidate not in existing_ids:
            return candidate
        entry_number += 1


def next_goal_id(tasks: list[dict[str, Any]], now: datetime | None = None) -> str:
    current_time = now or now_utc_datetime()
    date_prefix = current_time.date().isoformat()
    prefix = f"{date_prefix}-"
    max_suffix = 0

    for task in tasks:
        goal_id = task.get("goal_id")
        if not isinstance(goal_id, str) or not goal_id.startswith(prefix):
            continue
        suffix = goal_id.removeprefix(prefix)
        if len(suffix) != 3 or not suffix.isdigit():
            continue
        max_suffix = max(max_suffix, int(suffix))

    return f"{date_prefix}-{max_suffix + 1:03d}"


def compute_numeric_delta(previous_value: float | int | None, current_value: float | int | None) -> float | int | None:
    if current_value is None:
        return None
    if previous_value is None:
        return current_value
    delta = current_value - previous_value
    if delta <= 0:
        return None
    return delta


def build_attempt_entry(
    *,
    entries: list[dict[str, Any]],
    goal: dict[str, Any],
    inferred: bool,
    status: str,
    started_at: str | None,
    finished_at: str | None,
    cost_usd: float | None,
    tokens_total: int | None,
    failure_reason: str | None,
    notes: str | None,
) -> dict[str, Any]:
    entry = entry_to_dict(
        AttemptEntryRecord(
            entry_id=next_entry_id(entries, goal["goal_id"]),
            goal_id=goal["goal_id"],
            entry_type=goal["goal_type"],
            inferred=inferred,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            cost_usd=cost_usd,
            tokens_total=tokens_total,
            failure_reason=failure_reason,
            notes=notes,
        )
    )
    validate_entry_record(entry)
    return entry


def close_open_attempt_entry(entry: dict[str, Any], finished_at: str | None, notes: str | None) -> None:
    if entry["status"] != "in_progress":
        return
    entry["status"] = "fail"
    entry["inferred"] = True
    entry["failure_reason"] = entry.get("failure_reason")
    entry["finished_at"] = finished_at or now_utc_iso()
    if notes:
        existing_notes = entry.get("notes")
        entry["notes"] = notes if not existing_notes else f"{existing_notes} | {notes}"


def trim_excess_attempt_entries(
    entries: list[dict[str, Any]],
    goal_entries: list[dict[str, Any]],
    current_attempts: int,
) -> None:
    while len(goal_entries) > current_attempts:
        removed_entry = goal_entries.pop()
        entries.remove(removed_entry)


def close_previous_open_attempt(
    goal_entries: list[dict[str, Any]],
    current_attempts: int,
    finished_at: str | None,
) -> None:
    if current_attempts > len(goal_entries) and goal_entries:
        close_open_attempt_entry(
            goal_entries[-1],
            finished_at=finished_at,
            notes="Inferred failed attempt because a newer attempt was started.",
        )


def append_missing_attempt_entries(
    *,
    entries: list[dict[str, Any]],
    goal_entries: list[dict[str, Any]],
    goal: dict[str, Any],
    current_attempts: int,
) -> None:
    while len(goal_entries) < current_attempts:
        is_latest_attempt = len(goal_entries) + 1 == current_attempts
        inferred_failed_attempt = not is_latest_attempt
        entry_status = goal["status"] if is_latest_attempt else "fail"
        inferred_timestamp = goal.get("started_at") or now_utc_iso()
        entry_finished_at = goal.get("finished_at") if entry_status in {"success", "fail"} else None
        if inferred_failed_attempt:
            entry_finished_at = inferred_timestamp
        started_at = goal.get("started_at") if not goal_entries else now_utc_iso()
        if inferred_failed_attempt:
            started_at = inferred_timestamp
        elif entry_finished_at is not None:
            started_at = goal.get("started_at") or entry_finished_at
        notes = goal.get("notes")
        if inferred_failed_attempt:
            notes = "Inferred historical failed attempt from attempts count."
        entry = build_attempt_entry(
            entries=entries,
            goal=goal,
            inferred=inferred_failed_attempt,
            status=entry_status,
            started_at=started_at,
            finished_at=entry_finished_at,
            cost_usd=None,
            tokens_total=None,
            failure_reason=goal.get("failure_reason") if entry_status == "fail" and is_latest_attempt else None,
            notes=notes,
        )
        entries.append(entry)
        goal_entries.append(entry)


def update_latest_attempt_entry(goal_entries: list[dict[str, Any]], goal: dict[str, Any]) -> dict[str, Any] | None:
    if not goal_entries:
        return None
    latest_entry = goal_entries[-1]
    latest_entry["entry_type"] = goal["goal_type"]
    latest_entry["inferred"] = bool(latest_entry.get("inferred", False))
    latest_entry["status"] = goal["status"]
    latest_entry["started_at"] = latest_entry.get("started_at") or goal.get("started_at")
    latest_entry["finished_at"] = goal.get("finished_at") if goal["status"] in {"success", "fail"} else None
    latest_entry["failure_reason"] = goal.get("failure_reason")
    latest_entry["notes"] = goal.get("notes")
    return latest_entry


def apply_attempt_usage_deltas(
    latest_entry: dict[str, Any],
    goal: dict[str, Any],
    previous_goal: dict[str, Any] | None,
) -> None:
    previous_cost = None if previous_goal is None else previous_goal.get("cost_usd")
    previous_tokens = None if previous_goal is None else previous_goal.get("tokens_total")
    cost_delta = compute_numeric_delta(previous_cost, goal.get("cost_usd"))
    token_delta = compute_numeric_delta(previous_tokens, goal.get("tokens_total"))
    if cost_delta is not None:
        latest_entry["cost_usd"] = round_usd(cost_delta) if isinstance(cost_delta, float) else round_usd(float(cost_delta))
    elif previous_goal is None and goal.get("cost_usd") is not None:
        latest_entry["cost_usd"] = goal.get("cost_usd")
    if token_delta is not None:
        latest_entry["tokens_total"] = int(token_delta)
    elif previous_goal is None and goal.get("tokens_total") is not None:
        latest_entry["tokens_total"] = goal.get("tokens_total")


def validate_goal_entries(goal_entries: list[dict[str, Any]]) -> None:
    for entry in goal_entries:
        validate_entry_record(entry)


def sync_goal_attempt_entries(
    data: dict[str, Any],
    goal: dict[str, Any],
    previous_goal: dict[str, Any] | None,
) -> None:
    entries: list[dict[str, Any]] = data["entries"]
    goal_entries = get_goal_entries(entries, goal["goal_id"])
    goal_entries.sort(key=lambda entry: entry.get("started_at") or "")

    current_attempts = int(goal.get("attempts") or 0)

    trim_excess_attempt_entries(entries, goal_entries, current_attempts)
    close_previous_open_attempt(
        goal_entries,
        current_attempts,
        goal.get("finished_at"),
    )
    append_missing_attempt_entries(
        entries=entries,
        goal_entries=goal_entries,
        goal=goal,
        current_attempts=current_attempts,
    )

    if current_attempts == 0 or not goal_entries:
        return

    latest_entry = update_latest_attempt_entry(goal_entries, goal)
    if latest_entry is None:
        return
    apply_attempt_usage_deltas(latest_entry, goal, previous_goal)
    validate_goal_entries(goal_entries)


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


def create_goal_record(
    *,
    tasks: list[dict[str, Any]],
    task_id: str,
    title: str | None,
    task_type: str | None,
    linked_task_id: str | None,
    started_at: str | None,
) -> GoalRecord:
    if title is None:
        raise ValueError("title is required when creating a new task")
    if task_type is None:
        raise ValueError("task_type is required when creating a new task")

    validate_task_type(task_type)
    if linked_task_id is not None:
        linked_task = get_task(tasks, linked_task_id)
        if linked_task is not None and linked_task["goal_type"] != task_type:
            raise ValueError("linked tasks must use the same task_type")

    new_goal = GoalRecord(
        goal_id=task_id,
        title=title,
        goal_type=task_type,
        supersedes_goal_id=linked_task_id,
        status="in_progress",
        attempts=0,
        started_at=started_at or now_utc_iso(),
        finished_at=None,
        cost_usd=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
    )
    tasks.append(goal_to_dict(new_goal))
    return new_goal


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


def apply_goal_updates(
    *,
    entries: list[dict[str, Any]],
    task: GoalRecord,
    title: str | None,
    task_type: str | None,
    status: str | None,
    attempts_delta: int | None,
    attempts_abs: int | None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    usage_cost_usd: float | None,
    usage_total_tokens: int | None,
    auto_cost_usd: float | None,
    auto_total_tokens: int | None,
    failure_reason: str | None,
    notes: str | None,
    started_at: str | None,
    finished_at: str | None,
) -> None:
    if title is not None:
        if not title.strip():
            raise ValueError("title cannot be empty")
        task.title = title
    if task_type is not None:
        validate_task_type(task_type)
        ensure_goal_type_update_allowed(entries, task, task_type)
        task.goal_type = task_type
    if status is not None:
        validate_status(status)
        task.status = status
    if attempts_abs is not None:
        validate_non_negative_int(attempts_abs, "attempts")
        task.attempts = attempts_abs
    if attempts_delta is not None:
        validate_non_negative_int(attempts_delta, "attempts_delta")
        task.attempts = task.attempts + attempts_delta

    if cost_usd_set is not None:
        validate_non_negative_float(cost_usd_set, "cost_usd")
        task.cost_usd = cost_usd_set
    elif cost_usd_add is not None:
        validate_non_negative_float(cost_usd_add, "cost_usd_add")
        current_cost = task.cost_usd or 0.0
        task.cost_usd = round_usd(float(current_cost) + cost_usd_add)
    elif usage_cost_usd is not None:
        current_cost = task.cost_usd or 0.0
        task.cost_usd = round_usd(float(current_cost) + usage_cost_usd)
    elif auto_cost_usd is not None:
        task.cost_usd = auto_cost_usd

    if tokens_set is not None:
        validate_non_negative_int(tokens_set, "tokens")
        task.tokens_total = tokens_set
    elif tokens_add is not None:
        validate_non_negative_int(tokens_add, "tokens_add")
        current_tokens = task.tokens_total or 0
        task.tokens_total = current_tokens + tokens_add
    elif usage_total_tokens is not None:
        current_tokens = task.tokens_total or 0
        task.tokens_total = current_tokens + usage_total_tokens
    elif auto_total_tokens is not None:
        task.tokens_total = auto_total_tokens

    if failure_reason is not None:
        validate_failure_reason(failure_reason)
        task.failure_reason = failure_reason

    if notes is not None:
        task.notes = notes
    if started_at is not None:
        task.started_at = started_at
    if finished_at is not None:
        task.finished_at = finished_at


def finalize_goal_update(task: GoalRecord) -> None:
    if task.status in {"success", "fail"} and task.attempts == 0:
        task.attempts = 1
    if task.status in {"success", "fail"} and not task.finished_at:
        finished_dt = now_utc_datetime()
        started_at_value = task.started_at
        if started_at_value is not None:
            started_dt = parse_iso_datetime(started_at_value, "started_at")
            if finished_dt < started_dt:
                finished_dt = started_dt
        task.finished_at = finished_dt.isoformat()
    if task.status == "success":
        task.failure_reason = None

    validate_goal_record(goal_to_dict(task))


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


def print_summary(data: dict[str, Any]) -> None:
    summary = data["summary"]
    operator_review = build_operator_review(summary)
    print("Codex Metrics Summary")
    print(f"Closed goals: {summary['closed_tasks']}")
    print(f"Successes: {summary['successes']}")
    print(f"Fails: {summary['fails']}")
    print(f"Total attempts: {summary['total_attempts']}")
    print(f"Known total cost (USD): {format_usd(summary['total_cost_usd'])}")
    print(f"Known total tokens: {summary['total_tokens']}")
    print(f"Success Rate: {format_pct(summary['success_rate'])}")
    print(f"Attempts per Closed Goal: {format_num(summary['attempts_per_closed_task'])}")
    print(f"Known cost coverage: {format_coverage(summary['known_cost_successes'], summary['successes'])} successful goals")
    print(f"Known token coverage: {format_coverage(summary['known_token_successes'], summary['successes'])} successful goals")
    print(f"Complete cost coverage: {format_coverage(summary['complete_cost_successes'], summary['successes'])} successful goals")
    print(f"Complete token coverage: {format_coverage(summary['complete_token_successes'], summary['successes'])} successful goals")
    print(f"Known Cost per Success (USD): {format_usd(summary['known_cost_per_success_usd'])}")
    print(f"Known Cost per Success (Tokens): {format_num(summary['known_cost_per_success_tokens'])}")
    print(f"Complete Cost per Covered Success (USD): {format_usd(summary['complete_cost_per_covered_success_usd'])}")
    print(f"Complete Cost per Covered Success (Tokens): {format_num(summary['complete_cost_per_covered_success_tokens'])}")
    print(f"Closed entries: {summary['entries']['closed_entries']}")
    print(f"Entry successes: {summary['entries']['successes']}")
    print(f"Entry fails: {summary['entries']['fails']}")
    print(f"Entry Success Rate: {format_pct(summary['entries']['success_rate'])}")
    print("Operator review:")
    for line in operator_review:
        print(f"- {line}")
    for task_type in ("product", "retro", "meta"):
        type_summary = summary["by_goal_type"][task_type]
        print(f"{task_type.title()} goals: {type_summary['closed_tasks']} closed, {type_summary['successes']} successes, {type_summary['fails']} fails")
    if summary["entries"]["failure_reasons"]:
        print("Entry failure reasons:")
        for reason, count in summary["entries"]["failure_reasons"].items():
            print(f"- {reason}: {count}")


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
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        with metrics_mutation_lock(metrics_path):
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
        with metrics_mutation_lock(metrics_path):
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

    if args.command == "merge-tasks":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        with metrics_mutation_lock(metrics_path):
            data = load_metrics(metrics_path)
            task = merge_tasks(
                data=data,
                keep_task_id=args.keep_task_id,
                drop_task_id=args.drop_task_id,
            )
            recompute_summary(data)
            save_metrics(metrics_path, data)
            save_report(report_path, data)
        print(f"Merged goal {args.drop_task_id} into {args.keep_task_id}")
        print(f"Status: {task['status']}")
        print(f"Attempts: {task['attempts']}")
        print_summary(data)
        return 0

    if args.command == "update":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        pricing_path = Path(args.pricing_path)
        codex_state_path = Path(args.codex_state_path)
        codex_logs_path = Path(args.codex_logs_path)
        with metrics_mutation_lock(metrics_path):
            data = load_metrics(metrics_path)
            previous_task = None
            existing_task = None
            if args.task_id is not None:
                existing_task = get_task(data["goals"], args.task_id)
            if existing_task is not None:
                previous_task = dict(existing_task)

            task = upsert_task(
                data=data,
                task_id=args.task_id,
                title=args.title,
                task_type=args.task_type,
                continuation_of=args.continuation_of,
                supersedes_task_id=args.supersedes_task_id,
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

            sync_goal_attempt_entries(data, task, previous_task)
            recompute_summary(data)
            save_metrics(metrics_path, data)
            save_report(report_path, data)

        print(f"Updated goal {task['goal_id']}")
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
