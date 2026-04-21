"""Dataclass ↔ ndjson-dict conversion for the canonical goal/entry records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_agents_metrics.domain.models import AttemptEntryRecord, EffectiveGoalRecord, GoalRecord
from ai_agents_metrics.domain.time_utils import parse_iso_datetime_flexible


def _parse_ts(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    return parse_iso_datetime_flexible(value, field)


def _dump_ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def goal_from_dict(goal: dict[str, Any]) -> GoalRecord:
    return GoalRecord(
        goal_id=goal["goal_id"],
        title=goal["title"],
        goal_type=goal["goal_type"],
        supersedes_goal_id=goal.get("supersedes_goal_id"),
        status=goal["status"],
        attempts=int(goal["attempts"]),
        started_at=_parse_ts(goal.get("started_at"), "started_at"),
        finished_at=_parse_ts(goal.get("finished_at"), "finished_at"),
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
    return {
        "goal_id": goal.goal_id,
        "title": goal.title,
        "goal_type": goal.goal_type,
        "supersedes_goal_id": goal.supersedes_goal_id,
        "status": goal.status,
        "attempts": goal.attempts,
        "started_at": _dump_ts(goal.started_at),
        "finished_at": _dump_ts(goal.finished_at),
        "cost_usd": goal.cost_usd,
        "input_tokens": goal.input_tokens,
        "cached_input_tokens": goal.cached_input_tokens,
        "output_tokens": goal.output_tokens,
        "tokens_total": goal.tokens_total,
        "failure_reason": goal.failure_reason,
        "notes": goal.notes,
        "agent_name": goal.agent_name,
        "result_fit": goal.result_fit,
        "model": goal.model,
    }


def entry_from_dict(entry: dict[str, Any]) -> AttemptEntryRecord:
    return AttemptEntryRecord(
        entry_id=entry["entry_id"],
        goal_id=entry["goal_id"],
        entry_type=entry["entry_type"],
        inferred=bool(entry.get("inferred", False)),
        status=entry["status"],
        started_at=_parse_ts(entry.get("started_at"), "started_at"),
        finished_at=_parse_ts(entry.get("finished_at"), "finished_at"),
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
    return {
        "entry_id": entry.entry_id,
        "goal_id": entry.goal_id,
        "entry_type": entry.entry_type,
        "inferred": entry.inferred,
        "status": entry.status,
        "started_at": _dump_ts(entry.started_at),
        "finished_at": _dump_ts(entry.finished_at),
        "cost_usd": entry.cost_usd,
        "input_tokens": entry.input_tokens,
        "cached_input_tokens": entry.cached_input_tokens,
        "output_tokens": entry.output_tokens,
        "tokens_total": entry.tokens_total,
        "failure_reason": entry.failure_reason,
        "notes": entry.notes,
        "agent_name": entry.agent_name,
        "model": entry.model,
    }


def effective_goal_to_dict(goal: EffectiveGoalRecord) -> dict[str, Any]:
    return {
        "goal_id": goal.goal_id,
        "title": goal.title,
        "goal_type": goal.goal_type,
        "status": goal.status,
        "attempts": goal.attempts,
        "started_at": _dump_ts(goal.started_at),
        "finished_at": _dump_ts(goal.finished_at),
        "cost_usd": goal.cost_usd,
        "cost_usd_known": goal.cost_usd_known,
        "cost_complete": goal.cost_complete,
        "input_tokens": goal.input_tokens,
        "input_tokens_known": goal.input_tokens_known,
        "cached_input_tokens": goal.cached_input_tokens,
        "cached_input_tokens_known": goal.cached_input_tokens_known,
        "output_tokens": goal.output_tokens,
        "output_tokens_known": goal.output_tokens_known,
        "token_breakdown_complete": goal.token_breakdown_complete,
        "tokens_total": goal.tokens_total,
        "tokens_total_known": goal.tokens_total_known,
        "tokens_complete": goal.tokens_complete,
        "failure_reason": goal.failure_reason,
        "notes": goal.notes,
        "supersedes_goal_id": goal.supersedes_goal_id,
        "result_fit": goal.result_fit,
        "model": goal.model,
        "model_complete": goal.model_complete,
        "model_consistent": goal.model_consistent,
    }
