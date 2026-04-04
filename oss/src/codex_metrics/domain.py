from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, TypeVar

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
ALLOWED_RESULT_FITS = {"exact_fit", "partial_fit", "miss"}


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
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None
    agent_name: str | None = None
    result_fit: str | None = None
    model: str | None = None


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
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None
    agent_name: str | None = None
    model: str | None = None


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
    input_tokens: int | None
    input_tokens_known: int | None
    cached_input_tokens: int | None
    cached_input_tokens_known: int | None
    output_tokens: int | None
    output_tokens_known: int | None
    token_breakdown_complete: bool
    tokens_total: int | None
    tokens_total_known: int | None
    tokens_complete: bool
    failure_reason: str | None
    notes: str | None
    supersedes_goal_id: str | None
    result_fit: str | None = None
    model: str | None = None
    model_complete: bool = False
    model_consistent: bool = False


StatusRecordT = TypeVar("StatusRecordT", GoalRecord, AttemptEntryRecord, EffectiveGoalRecord)


LEGACY_GOAL_SUPERSEDES_MAP = {
    "2026-03-29-008": "2026-03-29-007",
}


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
        input_tokens=None if goal.get("input_tokens") is None else int(goal["input_tokens"]),
        cached_input_tokens=None if goal.get("cached_input_tokens") is None else int(goal["cached_input_tokens"]),
        output_tokens=None if goal.get("output_tokens") is None else int(goal["output_tokens"]),
        tokens_total=None if goal.get("tokens_total") is None else int(goal["tokens_total"]),
        failure_reason=goal.get("failure_reason"),
        notes=goal.get("notes"),
        agent_name=goal.get("agent_name"),
        result_fit=goal.get("result_fit"),
        model=None if goal.get("model") is None else str(goal["model"]).strip(),
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
        input_tokens=None if entry.get("input_tokens") is None else int(entry["input_tokens"]),
        cached_input_tokens=None if entry.get("cached_input_tokens") is None else int(entry["cached_input_tokens"]),
        output_tokens=None if entry.get("output_tokens") is None else int(entry["output_tokens"]),
        tokens_total=None if entry.get("tokens_total") is None else int(entry["tokens_total"]),
        failure_reason=entry.get("failure_reason"),
        notes=entry.get("notes"),
        agent_name=entry.get("agent_name"),
        model=None if entry.get("model") is None else str(entry["model"]).strip(),
    )


def entry_to_dict(entry: AttemptEntryRecord) -> dict[str, Any]:
    return asdict(entry)


def effective_goal_to_dict(goal: EffectiveGoalRecord) -> dict[str, Any]:
    return asdict(goal)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_utc_datetime() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def empty_summary_block(include_by_task_type: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "closed_tasks": 0,
        "successes": 0,
        "fails": 0,
        "total_attempts": 0,
        "total_cost_usd": 0.0,
        "total_input_tokens": 0,
        "total_cached_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "success_rate": None,
        "attempts_per_closed_task": None,
        "known_cost_successes": 0,
        "known_token_successes": 0,
        "known_token_breakdown_successes": 0,
        "complete_cost_successes": 0,
        "complete_token_successes": 0,
        "complete_token_breakdown_successes": 0,
        "model_summary_goals": 0,
        "model_complete_goals": 0,
        "mixed_model_goals": 0,
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
        summary["by_model"] = {}
        summary["entries"] = {
            "closed_entries": 0,
            "successes": 0,
            "fails": 0,
            "success_rate": None,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_cached_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "failure_reasons": {},
        }
    return summary


def default_metrics() -> dict[str, Any]:
    return {
        "summary": empty_summary_block(include_by_task_type=True),
        "goals": [],
        "entries": [],
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
        raise ValueError(f"Invalid failure reason: {reason}. Allowed: {sorted(ALLOWED_FAILURE_REASONS)}")


def validate_result_fit(result_fit: str | None) -> None:
    if result_fit is None:
        return
    if result_fit not in ALLOWED_RESULT_FITS:
        raise ValueError(f"Invalid result_fit: {result_fit}. Allowed: {sorted(ALLOWED_RESULT_FITS)}")


def validate_agent_name(agent_name: str | None) -> None:
    if agent_name is None:
        return
    if not agent_name.strip():
        raise ValueError("agent_name cannot be empty")


def validate_non_negative_int(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def validate_non_negative_float(value: float, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def validate_model_name(model: str | None) -> None:
    if model is None:
        return
    if not model.strip():
        raise ValueError("model cannot be empty")


def validate_token_breakdown_consistency(
    *,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    tokens_total: int | None,
    field_name: str,
) -> None:
    if input_tokens is None or cached_input_tokens is None or output_tokens is None or tokens_total is None:
        return
    minimum_expected_total = input_tokens + cached_input_tokens + output_tokens
    if tokens_total < minimum_expected_total:
        raise ValueError(
            f"{field_name} cannot be smaller than input_tokens + cached_input_tokens + output_tokens when all are present"
        )


def validate_task_business_rules(task: dict[str, Any]) -> None:
    started_at = task.get("started_at")
    finished_at = task.get("finished_at")
    status = task["status"]
    attempts = task["attempts"]
    failure_reason = task.get("failure_reason")
    goal_type = task["goal_type"]
    result_fit = task.get("result_fit")
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
    if result_fit is not None and goal_type != "product":
        raise ValueError("result_fit is only allowed for product goals")
    if status == "in_progress" and result_fit is not None:
        raise ValueError("result_fit must be empty when status is in_progress")
    if status == "success" and result_fit == "miss":
        raise ValueError("result_fit miss is not allowed when status is success")
    if status == "fail" and result_fit not in {None, "miss"}:
        raise ValueError("failed product goals may only use result_fit miss")


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
        "input_tokens": (int, type(None)),
        "cached_input_tokens": (int, type(None)),
        "output_tokens": (int, type(None)),
        "tokens_total": (int, type(None)),
        "failure_reason": (str, type(None)),
        "notes": (str, type(None)),
    }

    for field_name, allowed_types in required_fields.items():
        if field_name not in goal:
            raise ValueError(f"Missing required goal field: {field_name}")
        if not isinstance(goal[field_name], allowed_types):
            raise ValueError(f"Invalid type for goal field: {field_name}")
    if "result_fit" in goal and not isinstance(goal["result_fit"], (str, type(None))):
        raise ValueError("Invalid type for goal field: result_fit")
    if "agent_name" in goal and not isinstance(goal["agent_name"], (str, type(None))):
        raise ValueError("Invalid type for goal field: agent_name")
    if "model" in goal and not isinstance(goal["model"], (str, type(None))):
        raise ValueError("Invalid type for goal field: model")

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
    if goal_record.input_tokens is not None:
        validate_non_negative_int(goal_record.input_tokens, "input_tokens")
    if goal_record.cached_input_tokens is not None:
        validate_non_negative_int(goal_record.cached_input_tokens, "cached_input_tokens")
    if goal_record.output_tokens is not None:
        validate_non_negative_int(goal_record.output_tokens, "output_tokens")
    if goal_record.tokens_total is not None:
        validate_non_negative_int(goal_record.tokens_total, "tokens_total")
    validate_token_breakdown_consistency(
        input_tokens=goal_record.input_tokens,
        cached_input_tokens=goal_record.cached_input_tokens,
        output_tokens=goal_record.output_tokens,
        tokens_total=goal_record.tokens_total,
        field_name="tokens_total",
    )

    validate_failure_reason(goal_record.failure_reason)
    validate_agent_name(goal_record.agent_name)
    validate_result_fit(goal_record.result_fit)
    validate_model_name(goal_record.model)
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
        "input_tokens": (int, type(None)),
        "cached_input_tokens": (int, type(None)),
        "output_tokens": (int, type(None)),
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
    if "agent_name" in entry and not isinstance(entry["agent_name"], (str, type(None))):
        raise ValueError("Invalid type for entry field: agent_name")
    if "model" in entry and not isinstance(entry["model"], (str, type(None))):
        raise ValueError("Invalid type for entry field: model")
    if entry_record.cost_usd is not None:
        validate_non_negative_float(entry_record.cost_usd, "cost_usd")
    if entry_record.input_tokens is not None:
        validate_non_negative_int(entry_record.input_tokens, "input_tokens")
    if entry_record.cached_input_tokens is not None:
        validate_non_negative_int(entry_record.cached_input_tokens, "cached_input_tokens")
    if entry_record.output_tokens is not None:
        validate_non_negative_int(entry_record.output_tokens, "output_tokens")
    if entry_record.tokens_total is not None:
        validate_non_negative_int(entry_record.tokens_total, "tokens_total")
    validate_token_breakdown_consistency(
        input_tokens=entry_record.input_tokens,
        cached_input_tokens=entry_record.cached_input_tokens,
        output_tokens=entry_record.output_tokens,
        tokens_total=entry_record.tokens_total,
        field_name="tokens_total",
    )
    validate_failure_reason(entry_record.failure_reason)
    validate_agent_name(entry_record.agent_name)
    validate_model_name(entry_record.model)
    validate_entry_business_rules(entry)


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


def validate_goal_supersession_graph(goals: list[dict[str, Any]]) -> None:
    goal_records = [goal_from_dict(goal) for goal in goals]
    goal_by_id = {goal.goal_id: goal for goal in goal_records}
    for goal in goal_records:
        build_goal_chain(goal_by_id, goal)


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
                    "input_tokens": task.get("input_tokens"),
                    "cached_input_tokens": task.get("cached_input_tokens"),
                    "output_tokens": task.get("output_tokens"),
                    "tokens_total": task.get("tokens_total"),
                    "failure_reason": task.get("failure_reason"),
                    "notes": task.get("notes"),
                    "agent_name": task.get("agent_name"),
                    "result_fit": task.get("result_fit"),
                    "model": task.get("model"),
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
                        "input_tokens": task.get("input_tokens"),
                        "cached_input_tokens": task.get("cached_input_tokens"),
                        "output_tokens": task.get("output_tokens"),
                        "tokens_total": task.get("tokens_total"),
                        "failure_reason": task.get("failure_reason"),
                        "notes": task.get("notes"),
                        "agent_name": task.get("agent_name"),
                        "model": task.get("model"),
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
            if isinstance(goal, dict) and "agent_name" not in goal:
                goal["agent_name"] = None
            if isinstance(goal, dict) and "result_fit" not in goal:
                goal["result_fit"] = None
            if isinstance(goal, dict) and "input_tokens" not in goal:
                goal["input_tokens"] = None
            if isinstance(goal, dict) and "cached_input_tokens" not in goal:
                goal["cached_input_tokens"] = None
            if isinstance(goal, dict) and "output_tokens" not in goal:
                goal["output_tokens"] = None

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
            if isinstance(entry, dict) and "agent_name" not in entry:
                entry["agent_name"] = None
            if isinstance(entry, dict) and "input_tokens" not in entry:
                entry["input_tokens"] = None
            if isinstance(entry, dict) and "cached_input_tokens" not in entry:
                entry["cached_input_tokens"] = None
            if isinstance(entry, dict) and "output_tokens" not in entry:
                entry["output_tokens"] = None


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_metrics()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    normalize_legacy_metrics_data(data)
    validate_metrics_data(data, path)
    return data


def get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int | None:
    for idx, task in enumerate(tasks):
        if task.get("goal_id") == task_id:
            return idx
    return None


def get_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    task_index = get_task_index(tasks, task_id)
    return None if task_index is None else tasks[task_index]


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


def aggregate_chain_token_component(chain: list[GoalRecord], field_name: str) -> tuple[int | None, int | None, bool]:
    known_values = [int(value) for goal in chain if (value := getattr(goal, field_name)) is not None]
    aggregated_known = sum(known_values) if known_values else None
    is_complete = len(known_values) == len(chain)
    aggregated_value = aggregated_known if is_complete else None
    return aggregated_value, aggregated_known, is_complete


def aggregate_chain_model(chain: list[GoalRecord]) -> tuple[str | None, bool, bool]:
    known_models = [goal.model for goal in chain if goal.model is not None]
    if not known_models:
        return None, False, False
    model_complete = len(known_models) == len(chain)
    model_consistent = len(set(known_models)) == 1
    aggregated_model = known_models[0] if model_complete and model_consistent else None
    return aggregated_model, model_complete, model_consistent


def aggregate_chain_timestamps(chain: list[GoalRecord]) -> tuple[str | None, str | None]:
    started_at = None
    finished_at = None
    for goal in chain:
        started_at = choose_earliest_timestamp(started_at, goal.started_at)
        finished_at = choose_latest_timestamp(finished_at, goal.finished_at)
    return started_at, finished_at


def build_effective_goal_record(terminal_goal: GoalRecord, chain: list[GoalRecord]) -> EffectiveGoalRecord:
    aggregated_cost, aggregated_cost_known, cost_complete = aggregate_chain_costs(chain)
    aggregated_input, aggregated_input_known, input_complete = aggregate_chain_token_component(chain, "input_tokens")
    aggregated_cached, aggregated_cached_known, cached_complete = aggregate_chain_token_component(chain, "cached_input_tokens")
    aggregated_output, aggregated_output_known, output_complete = aggregate_chain_token_component(chain, "output_tokens")
    aggregated_tokens, aggregated_tokens_known, tokens_complete = aggregate_chain_tokens(chain)
    aggregated_model, model_complete, model_consistent = aggregate_chain_model(chain)
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
        input_tokens=aggregated_input,
        input_tokens_known=aggregated_input_known,
        cached_input_tokens=aggregated_cached,
        cached_input_tokens_known=aggregated_cached_known,
        output_tokens=aggregated_output,
        output_tokens_known=aggregated_output_known,
        token_breakdown_complete=input_complete and cached_complete and output_complete,
        tokens_total=aggregated_tokens,
        tokens_total_known=aggregated_tokens_known,
        tokens_complete=tokens_complete,
        failure_reason=terminal_goal.failure_reason,
        notes=terminal_goal.notes,
        supersedes_goal_id=terminal_goal.supersedes_goal_id,
        result_fit=terminal_goal.result_fit,
        model=aggregated_model,
        model_complete=model_complete,
        model_consistent=model_consistent,
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
    total_input_tokens_raw = sum_known_numeric_values(closed_tasks, "input_tokens_known", int)
    total_cached_input_tokens_raw = sum_known_numeric_values(closed_tasks, "cached_input_tokens_known", int)
    total_output_tokens_raw = sum_known_numeric_values(closed_tasks, "output_tokens_known", int)
    total_cost_usd = float(total_cost_usd_raw) if total_cost_usd_raw is not None else 0.0
    total_tokens_raw = sum_known_numeric_values(closed_tasks, "tokens_total_known", int)
    total_tokens = int(total_tokens_raw) if total_tokens_raw is not None else 0

    success_rate = (len(successes) / len(closed_tasks)) if closed_tasks else None
    attempts_per_closed_task = (total_attempts / len(closed_tasks)) if closed_tasks else None

    success_cost_values = [t.cost_usd for t in successes if t.cost_complete and t.cost_usd is not None]
    known_success_cost_values = [t.cost_usd_known for t in successes if t.cost_usd_known is not None]
    complete_cost_per_covered_success_usd = (
        float(sum(success_cost_values)) / len(success_cost_values) if success_cost_values else None
    )
    cost_per_success_usd = (
        float(sum(success_cost_values)) / len(successes)
        if successes and len(success_cost_values) == len(successes)
        else None
    )
    known_cost_per_success_usd = (
        float(sum(known_success_cost_values)) / len(known_success_cost_values) if known_success_cost_values else None
    )

    success_token_values = [t.tokens_total for t in successes if t.tokens_complete and t.tokens_total is not None]
    known_success_token_values = [t.tokens_total_known for t in successes if t.tokens_total_known is not None]
    known_success_breakdown_values = [t for t in successes if t.input_tokens_known is not None and t.cached_input_tokens_known is not None and t.output_tokens_known is not None]
    complete_success_breakdown_values = [t for t in successes if t.token_breakdown_complete]
    model_summary_goals = [t for t in closed_tasks if t.model is not None]
    model_complete_goals = [t for t in closed_tasks if t.model_complete]
    mixed_model_goals = [t for t in closed_tasks if t.model_complete and not t.model_consistent]
    complete_cost_per_covered_success_tokens = (
        sum(success_token_values) / len(success_token_values) if success_token_values else None
    )
    cost_per_success_tokens = (
        sum(success_token_values) / len(successes)
        if successes and len(success_token_values) == len(successes)
        else None
    )
    known_cost_per_success_tokens = (
        sum(known_success_token_values) / len(known_success_token_values) if known_success_token_values else None
    )

    return {
        "closed_tasks": len(closed_tasks),
        "successes": len(successes),
        "fails": len(fails),
        "total_attempts": total_attempts,
        "total_cost_usd": round_usd(total_cost_usd),
        "total_input_tokens": int(total_input_tokens_raw) if total_input_tokens_raw is not None else 0,
        "total_cached_input_tokens": int(total_cached_input_tokens_raw) if total_cached_input_tokens_raw is not None else 0,
        "total_output_tokens": int(total_output_tokens_raw) if total_output_tokens_raw is not None else 0,
        "total_tokens": total_tokens,
        "success_rate": success_rate,
        "attempts_per_closed_task": attempts_per_closed_task,
        "known_cost_successes": len(known_success_cost_values),
        "known_token_successes": len(known_success_token_values),
        "known_token_breakdown_successes": len(known_success_breakdown_values),
        "complete_cost_successes": len(success_cost_values),
        "complete_token_successes": len(success_token_values),
        "complete_token_breakdown_successes": len(complete_success_breakdown_values),
        "model_summary_goals": len(model_summary_goals),
        "model_complete_goals": len(model_complete_goals),
        "mixed_model_goals": len(mixed_model_goals),
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
    superseded_goal_ids = {goal.supersedes_goal_id for goal in goals if goal.supersedes_goal_id is not None}
    effective_goals: list[EffectiveGoalRecord] = []

    for terminal_goal in goals:
        if terminal_goal.goal_id in superseded_goal_ids:
            continue
        chain = build_goal_chain(goal_by_id, terminal_goal)
        effective_goals.append(build_effective_goal_record(terminal_goal, chain))

    return effective_goals


def build_model_summary(tasks: list[EffectiveGoalRecord]) -> dict[str, Any]:
    closed_tasks = get_closed_records(tasks)
    known_models = sorted({goal.model for goal in closed_tasks if goal.model is not None})
    return {
        model: compute_summary_block([goal for goal in closed_tasks if goal.model == model])
        for model in known_models
    }


def compute_entry_summary(entries: list[AttemptEntryRecord]) -> dict[str, Any]:
    closed_entries = get_closed_records(entries)
    successes = get_successful_records(closed_entries)
    fails = get_failed_records(closed_entries)
    total_cost_usd_raw = sum_known_numeric_values(closed_entries, "cost_usd", float)
    total_input_tokens_raw = sum_known_numeric_values(closed_entries, "input_tokens", int)
    total_cached_input_tokens_raw = sum_known_numeric_values(closed_entries, "cached_input_tokens", int)
    total_output_tokens_raw = sum_known_numeric_values(closed_entries, "output_tokens", int)
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
        "total_input_tokens": int(total_input_tokens_raw) if total_input_tokens_raw is not None else 0,
        "total_cached_input_tokens": int(total_cached_input_tokens_raw) if total_cached_input_tokens_raw is not None else 0,
        "total_output_tokens": int(total_output_tokens_raw) if total_output_tokens_raw is not None else 0,
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
    summary["by_model"] = build_model_summary(effective_goal_records)
    summary["entries"] = compute_entry_summary(entry_records)
    data["summary"] = summary


def get_goal_entries(entries: list[dict[str, Any]], goal_id: str) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry.get("goal_id") == goal_id]


def ensure_goal_type_update_allowed(entries: list[dict[str, Any]], goal: GoalRecord, new_goal_type: str | None) -> None:
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
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    tokens_total: int | None,
    failure_reason: str | None,
    notes: str | None,
    agent_name: str | None,
    model: str | None,
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
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            tokens_total=tokens_total,
            failure_reason=failure_reason,
            notes=notes,
            agent_name=agent_name,
            model=model,
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


def close_previous_open_attempt(goal_entries: list[dict[str, Any]], current_attempts: int, finished_at: str | None) -> None:
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
            input_tokens=None,
            cached_input_tokens=None,
            output_tokens=None,
            tokens_total=None,
            failure_reason=goal.get("failure_reason") if entry_status == "fail" and is_latest_attempt else None,
            notes=notes,
            agent_name=goal.get("agent_name"),
            model=goal.get("model") if is_latest_attempt else None,
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
    latest_entry["agent_name"] = goal.get("agent_name")
    if goal.get("model") is not None:
        latest_entry["model"] = goal.get("model")
    return latest_entry


def apply_attempt_usage_deltas(latest_entry: dict[str, Any], goal: dict[str, Any], previous_goal: dict[str, Any] | None) -> None:
    previous_cost = None if previous_goal is None else previous_goal.get("cost_usd")
    previous_input_tokens = None if previous_goal is None else previous_goal.get("input_tokens")
    previous_cached_input_tokens = None if previous_goal is None else previous_goal.get("cached_input_tokens")
    previous_output_tokens = None if previous_goal is None else previous_goal.get("output_tokens")
    previous_tokens = None if previous_goal is None else previous_goal.get("tokens_total")
    cost_delta = compute_numeric_delta(previous_cost, goal.get("cost_usd"))
    input_delta = compute_numeric_delta(previous_input_tokens, goal.get("input_tokens"))
    cached_input_delta = compute_numeric_delta(previous_cached_input_tokens, goal.get("cached_input_tokens"))
    output_delta = compute_numeric_delta(previous_output_tokens, goal.get("output_tokens"))
    token_delta = compute_numeric_delta(previous_tokens, goal.get("tokens_total"))
    if cost_delta is not None:
        latest_entry["cost_usd"] = round_usd(cost_delta) if isinstance(cost_delta, float) else round_usd(float(cost_delta))
    elif previous_goal is None and goal.get("cost_usd") is not None:
        latest_entry["cost_usd"] = goal.get("cost_usd")
    if input_delta is not None:
        latest_entry["input_tokens"] = int(input_delta)
    elif previous_goal is None and goal.get("input_tokens") is not None:
        latest_entry["input_tokens"] = goal.get("input_tokens")
    if cached_input_delta is not None:
        latest_entry["cached_input_tokens"] = int(cached_input_delta)
    elif previous_goal is None and goal.get("cached_input_tokens") is not None:
        latest_entry["cached_input_tokens"] = goal.get("cached_input_tokens")
    if output_delta is not None:
        latest_entry["output_tokens"] = int(output_delta)
    elif previous_goal is None and goal.get("output_tokens") is not None:
        latest_entry["output_tokens"] = goal.get("output_tokens")
    if token_delta is not None:
        latest_entry["tokens_total"] = int(token_delta)
    elif previous_goal is None and goal.get("tokens_total") is not None:
        latest_entry["tokens_total"] = goal.get("tokens_total")


def refresh_goal_model_summary(goal: dict[str, Any], goal_entries: list[dict[str, Any]]) -> None:
    entry_models = [entry.get("model") for entry in goal_entries]
    if not entry_models or any(model is None for model in entry_models):
        goal["model"] = None
        return

    distinct_models = sorted({str(model).strip() for model in entry_models if model is not None})
    if len(distinct_models) == 1:
        goal["model"] = distinct_models[0]
    else:
        goal["model"] = None


def validate_goal_entries(goal_entries: list[dict[str, Any]]) -> None:
    for entry in goal_entries:
        validate_entry_record(entry)


def sync_goal_attempt_entries(data: dict[str, Any], goal: dict[str, Any], previous_goal: dict[str, Any] | None) -> None:
    entries: list[dict[str, Any]] = data["entries"]
    goal_entries = get_goal_entries(entries, goal["goal_id"])
    goal_entries.sort(key=lambda entry: entry.get("started_at") or "")

    current_attempts = int(goal.get("attempts") or 0)
    trim_excess_attempt_entries(entries, goal_entries, current_attempts)
    close_previous_open_attempt(goal_entries, current_attempts, goal.get("finished_at"))
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
    refresh_goal_model_summary(goal, goal_entries)
    validate_goal_entries(goal_entries)
    validate_goal_record(goal)


def create_goal_record(
    *,
    tasks: list[dict[str, Any]],
    task_id: str,
    title: str | None,
    task_type: str | None,
    linked_task_id: str | None,
    started_at: str | None,
    model: str | None = None,
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
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
        agent_name=None,
        result_fit=None,
        model=model,
    )
    tasks.append(goal_to_dict(new_goal))
    return new_goal


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
    input_tokens_add: int | None,
    cached_input_tokens_add: int | None,
    output_tokens_add: int | None,
    tokens_add: int | None,
    tokens_set: int | None,
    usage_cost_usd: float | None,
    usage_input_tokens: int | None,
    usage_cached_input_tokens: int | None,
    usage_output_tokens: int | None,
    usage_total_tokens: int | None,
    auto_cost_usd: float | None,
    auto_input_tokens: int | None,
    auto_cached_input_tokens: int | None,
    auto_output_tokens: int | None,
    auto_total_tokens: int | None,
    model: str | None,
    usage_model: str | None,
    auto_model: str | None,
    failure_reason: str | None,
    notes: str | None,
    started_at: str | None,
    finished_at: str | None,
    agent_name: str | None = None,
    result_fit: str | None = None,
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

    if input_tokens_add is not None:
        validate_non_negative_int(input_tokens_add, "input_tokens_add")
        current_input_tokens = task.input_tokens or 0
        task.input_tokens = current_input_tokens + input_tokens_add
    elif usage_input_tokens is not None:
        current_input_tokens = task.input_tokens or 0
        task.input_tokens = current_input_tokens + usage_input_tokens
    elif auto_input_tokens is not None:
        task.input_tokens = auto_input_tokens

    if cached_input_tokens_add is not None:
        validate_non_negative_int(cached_input_tokens_add, "cached_input_tokens_add")
        current_cached_input_tokens = task.cached_input_tokens or 0
        task.cached_input_tokens = current_cached_input_tokens + cached_input_tokens_add
    elif usage_cached_input_tokens is not None:
        current_cached_input_tokens = task.cached_input_tokens or 0
        task.cached_input_tokens = current_cached_input_tokens + usage_cached_input_tokens
    elif auto_cached_input_tokens is not None:
        task.cached_input_tokens = auto_cached_input_tokens

    if output_tokens_add is not None:
        validate_non_negative_int(output_tokens_add, "output_tokens_add")
        current_output_tokens = task.output_tokens or 0
        task.output_tokens = current_output_tokens + output_tokens_add
    elif usage_output_tokens is not None:
        current_output_tokens = task.output_tokens or 0
        task.output_tokens = current_output_tokens + usage_output_tokens
    elif auto_output_tokens is not None:
        task.output_tokens = auto_output_tokens

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

    if usage_model is not None:
        validate_model_name(usage_model)
        task.model = usage_model
    elif model is not None:
        validate_model_name(model)
        task.model = model
    elif auto_model is not None:
        validate_model_name(auto_model)
        task.model = auto_model

    if failure_reason is not None:
        validate_failure_reason(failure_reason)
        task.failure_reason = failure_reason
    if result_fit is not None:
        validate_result_fit(result_fit)
        task.result_fit = result_fit
    if agent_name is not None:
        validate_agent_name(agent_name)
        task.agent_name = agent_name

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
    if (
        task.goal_type == "product"
        and task.status in {"success", "fail"}
        and task.cost_usd is None
        and task.tokens_total is None
        and task.started_at is not None
        and task.finished_at is not None
    ):
        started_dt = parse_iso_datetime(task.started_at, "started_at")
        finished_dt = parse_iso_datetime(task.finished_at, "finished_at")
        if started_dt == finished_dt:
            task.started_at = (started_dt - timedelta(seconds=1)).isoformat()
    if task.status == "success":
        task.failure_reason = None

    validate_goal_record(goal_to_dict(task))
