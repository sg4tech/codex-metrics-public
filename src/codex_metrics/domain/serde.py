from __future__ import annotations

from dataclasses import asdict
from typing import Any

from codex_metrics.domain.models import AttemptEntryRecord, EffectiveGoalRecord, GoalRecord


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
