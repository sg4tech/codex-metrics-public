"""Business-rule invariants for goals, entries, and metrics payloads."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_agents_metrics.domain.models import (
    ALLOWED_FAILURE_REASONS,
    ALLOWED_RESULT_FITS,
    ALLOWED_STATUSES,
    ALLOWED_TASK_TYPES,
    GoalRecord,
)
from ai_agents_metrics.domain.serde import entry_from_dict, goal_from_dict
from ai_agents_metrics.domain.time_utils import parse_iso_datetime


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


def validate_goal_entries(goal_entries: list[dict[str, Any]]) -> None:
    for entry in goal_entries:
        validate_entry_record(entry)
