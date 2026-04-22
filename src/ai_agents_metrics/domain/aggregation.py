"""Goal/entry/summary aggregation and the central ``apply_goal_updates`` mutator."""
# pylint: disable=too-many-lines  # domain/aggregation bundles goal/entry/summary aggregation and update application; splitting per stage is a tracked future task
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain.ids import next_entry_id
from ai_agents_metrics.domain.models import (
    ALLOWED_TASK_TYPES,
    EMPTY_GOAL_USAGE_RESOLUTION,
    AttemptEntryRecord,
    EffectiveGoalRecord,
    GoalRecord,
    GoalUsageResolution,
    ManualGoalUpdates,
    StatusRecordT,
)
from ai_agents_metrics.domain.serde import (
    entry_from_dict,
    entry_to_dict,
    goal_from_dict,
    goal_to_dict,
)
from ai_agents_metrics.domain.time_utils import (
    now_utc_datetime,
    now_utc_iso,
    parse_iso_datetime_flexible,
)
from ai_agents_metrics.domain.validation import (
    build_goal_chain,
    validate_agent_name,
    validate_entry_record,
    validate_failure_reason,
    validate_goal_entries,
    validate_goal_record,
    validate_metrics_data,
    validate_model_name,
    validate_non_negative_float,
    validate_non_negative_int,
    validate_result_fit,
    validate_status,
    validate_task_type,
)

if TYPE_CHECKING:
    from pathlib import Path


def round_usd(value: Decimal | float) -> float:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(decimal_value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


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
        "known_token_successes": 0,  # nosec B105
        "known_token_breakdown_successes": 0,  # nosec B105
        "complete_cost_successes": 0,
        "complete_token_successes": 0,  # nosec B105
        "complete_token_breakdown_successes": 0,  # nosec B105
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


def get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int | None:
    for idx, task in enumerate(tasks):
        if task.get("goal_id") == task_id:
            return idx
    return None


def get_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    task_index = get_task_index(tasks, task_id)
    return None if task_index is None else tasks[task_index]


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


def aggregate_chain_timestamps(chain: list[GoalRecord]) -> tuple[datetime | None, datetime | None]:
    started_at = None
    finished_at = None
    for goal in chain:
        if goal.started_at is not None and (started_at is None or goal.started_at < started_at):
            started_at = goal.started_at
        if goal.finished_at is not None and (finished_at is None or goal.finished_at > finished_at):
            finished_at = goal.finished_at
    return started_at, finished_at


def build_effective_goal_record(terminal_goal: GoalRecord, chain: list[GoalRecord]) -> EffectiveGoalRecord:
    # Aggregated chain results are kept as triples indexed inline in the
    # constructor so the local count stays under the limit even though
    # EffectiveGoalRecord is a wide canonical schema.
    cost = aggregate_chain_costs(chain)
    inp = aggregate_chain_token_component(chain, "input_tokens")
    cac = aggregate_chain_token_component(chain, "cached_input_tokens")
    out = aggregate_chain_token_component(chain, "output_tokens")
    tokens = aggregate_chain_tokens(chain)
    mdl = aggregate_chain_model(chain)
    started_at, finished_at = aggregate_chain_timestamps(chain)

    return EffectiveGoalRecord(
        goal_id=terminal_goal.goal_id,
        title=terminal_goal.title,
        goal_type=terminal_goal.goal_type,
        status=terminal_goal.status,
        attempts=sum(goal.attempts for goal in chain),
        started_at=started_at,
        finished_at=finished_at,
        cost_usd=cost[0],
        cost_usd_known=cost[1],
        cost_complete=cost[2],
        input_tokens=inp[0],
        input_tokens_known=inp[1],
        cached_input_tokens=cac[0],
        cached_input_tokens_known=cac[1],
        output_tokens=out[0],
        output_tokens_known=out[1],
        token_breakdown_complete=inp[2] and cac[2] and out[2],
        tokens_total=tokens[0],
        tokens_total_known=tokens[1],
        tokens_complete=tokens[2],
        failure_reason=terminal_goal.failure_reason,
        notes=terminal_goal.notes,
        supersedes_goal_id=terminal_goal.supersedes_goal_id,
        result_fit=terminal_goal.result_fit,
        model=mdl[0],
        model_complete=mdl[1],
        model_consistent=mdl[2],
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


def _compute_success_cost_metrics(successes: list[EffectiveGoalRecord]) -> dict[str, Any]:
    success_cost_values = [t.cost_usd for t in successes if t.cost_complete and t.cost_usd is not None]
    known_success_cost_values = [t.cost_usd_known for t in successes if t.cost_usd_known is not None]
    complete_cps_usd = float(sum(success_cost_values)) / len(success_cost_values) if success_cost_values else None
    cps_usd = (
        float(sum(success_cost_values)) / len(successes)
        if successes and len(success_cost_values) == len(successes)
        else None
    )
    known_cps_usd = (
        float(sum(known_success_cost_values)) / len(known_success_cost_values) if known_success_cost_values else None
    )
    return {
        "known_cost_successes": len(known_success_cost_values),
        "complete_cost_successes": len(success_cost_values),
        "known_cost_per_success_usd": round_usd(known_cps_usd) if known_cps_usd is not None else None,
        "complete_cost_per_covered_success_usd": round_usd(complete_cps_usd) if complete_cps_usd is not None else None,
        "cost_per_success_usd": round_usd(cps_usd) if cps_usd is not None else None,
    }


def _compute_success_token_metrics(
    successes: list[EffectiveGoalRecord],
    closed_tasks: list[EffectiveGoalRecord],
) -> dict[str, Any]:
    success_token_values = [t.tokens_total for t in successes if t.tokens_complete and t.tokens_total is not None]
    known_token_values = [t.tokens_total_known for t in successes if t.tokens_total_known is not None]
    known_breakdown_values = [
        t for t in successes
        if t.input_tokens_known is not None and t.cached_input_tokens_known is not None and t.output_tokens_known is not None
    ]
    complete_cps_tokens = sum(success_token_values) / len(success_token_values) if success_token_values else None
    cps_tokens = (
        sum(success_token_values) / len(successes)
        if successes and len(success_token_values) == len(successes)
        else None
    )
    known_cps_tokens = sum(known_token_values) / len(known_token_values) if known_token_values else None
    return {
        "known_token_successes": len(known_token_values),
        "known_token_breakdown_successes": len(known_breakdown_values),
        "complete_token_successes": len(success_token_values),
        "complete_token_breakdown_successes": len([t for t in successes if t.token_breakdown_complete]),
        "model_summary_goals": len([t for t in closed_tasks if t.model is not None]),
        "model_complete_goals": len([t for t in closed_tasks if t.model_complete]),
        "mixed_model_goals": len([t for t in closed_tasks if t.model_complete and not t.model_consistent]),
        "known_cost_per_success_tokens": known_cps_tokens,
        "complete_cost_per_covered_success_tokens": complete_cps_tokens,
        "cost_per_success_tokens": cps_tokens,
    }


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
        "success_rate": (len(successes) / len(closed_tasks)) if closed_tasks else None,
        "attempts_per_closed_task": (total_attempts / len(closed_tasks)) if closed_tasks else None,
        **_compute_success_cost_metrics(successes),
        **_compute_success_token_metrics(successes, closed_tasks),
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


def _migrate_legacy_tasks(data: dict[str, Any]) -> None:
    """Convert legacy ``tasks`` list to ``goals`` + ``entries`` in-place."""
    if "tasks" not in data or "goals" in data:
        return
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return
    legacy_goals: list[dict[str, Any]] = []
    legacy_entries: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_type = task.get("task_type", "product")
        supersedes_task_id = task.get("supersedes_task_id")
        task_id = task.get("task_id")
        legacy_goals.append({
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
        })
        legacy_entries.append({
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
        })
    data["goals"] = legacy_goals
    data["entries"] = legacy_entries


def _normalize_goal_fields(goals: list[Any]) -> None:
    for goal in goals:
        if not isinstance(goal, dict):
            continue
        if "goal_type" not in goal:
            goal["goal_type"] = goal.pop("task_type", "product")
        if "goal_id" not in goal:
            goal["goal_id"] = goal.pop("task_id")
        if "supersedes_goal_id" not in goal:
            goal["supersedes_goal_id"] = goal.pop("supersedes_task_id", None)
        if "agent_name" not in goal:
            goal["agent_name"] = None
        if "result_fit" not in goal:
            goal["result_fit"] = None
        if "input_tokens" not in goal:
            goal["input_tokens"] = None
        if "cached_input_tokens" not in goal:
            goal["cached_input_tokens"] = None
        if "output_tokens" not in goal:
            goal["output_tokens"] = None


def _normalize_entry_fields(entries: list[Any]) -> None:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "goal_id" not in entry:
            entry["goal_id"] = entry.get("task_id")
        if "entry_id" not in entry:
            entry["entry_id"] = entry.get("goal_id")
        if "entry_type" not in entry:
            entry["entry_type"] = entry.get("task_type", "update")
        if "agent_name" not in entry:
            entry["agent_name"] = None
        if "input_tokens" not in entry:
            entry["input_tokens"] = None
        if "cached_input_tokens" not in entry:
            entry["cached_input_tokens"] = None
        if "output_tokens" not in entry:
            entry["output_tokens"] = None


def normalize_legacy_metrics_data(data: dict[str, Any]) -> None:
    _migrate_legacy_tasks(data)
    goals: Any = data.get("goals")
    if isinstance(goals, list):
        _normalize_goal_fields(goals)
    entries: Any = data.get("entries")
    if not isinstance(entries, list) and isinstance(goals, list):
        data["entries"] = []
        entries = data["entries"]
    if isinstance(entries, list):
        _normalize_entry_fields(entries)


def load_metrics(path: Path) -> dict[str, Any]:
    # Lazy by contract: the "Domain layer must not import from CLI or
    # orchestration" import-linter rule treats event_store as infrastructure
    # that is only reached at runtime, not a module-level domain dependency.
    # pylint: disable-next=import-outside-toplevel
    from ai_agents_metrics.event_store import replay_events

    goals_list, entries_list = replay_events(path)
    data: dict[str, Any] = {
        "summary": empty_summary_block(include_by_task_type=True),
        "goals": goals_list,
        "entries": entries_list,
    }
    normalize_legacy_metrics_data(data)
    recompute_summary(data)
    validate_metrics_data(data, path)
    return data


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


def compute_numeric_delta(previous_value: float | int | None, current_value: float | int | None) -> float | int | None:
    if current_value is None:
        return None
    if previous_value is None:
        return current_value
    delta = current_value - previous_value
    if delta <= 0:
        return None
    return delta


def build_attempt_entry(record: AttemptEntryRecord) -> dict[str, Any]:
    """Serialize an AttemptEntryRecord into its dict form and validate invariants.

    Callers construct the record directly so the schema is a single point of
    truth — `AttemptEntryRecord` dictates both the struct and the storage
    dict shape.
    """
    entry = entry_to_dict(record)
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
            AttemptEntryRecord(
                entry_id=next_entry_id(entries, goal["goal_id"]),
                goal_id=goal["goal_id"],
                entry_type=goal["goal_type"],
                inferred=inferred_failed_attempt,
                status=entry_status,
                started_at=parse_iso_datetime_flexible(started_at, "started_at") if started_at is not None else None,
                finished_at=parse_iso_datetime_flexible(entry_finished_at, "finished_at") if entry_finished_at is not None else None,
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
        started_at=parse_iso_datetime_flexible(started_at, "started_at") if started_at is not None else now_utc_datetime(),
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


def _apply_cost_update(
    task: GoalRecord,
    cost_usd_set: float | None,
    cost_usd_add: float | None,
    usage_cost_usd: float | None,
    auto_cost_usd: float | None,
) -> None:
    if cost_usd_set is not None:
        validate_non_negative_float(cost_usd_set, "cost_usd")
        task.cost_usd = cost_usd_set
    elif cost_usd_add is not None:
        validate_non_negative_float(cost_usd_add, "cost_usd_add")
        task.cost_usd = round_usd(float(task.cost_usd or 0.0) + cost_usd_add)
    elif usage_cost_usd is not None:
        task.cost_usd = round_usd(float(task.cost_usd or 0.0) + usage_cost_usd)
    elif auto_cost_usd is not None:
        task.cost_usd = auto_cost_usd


def _apply_int_token_update(
    task: GoalRecord,
    field: str,
    validate_name: str,
    *,
    add_val: int | None,
    usage_val: int | None,
    auto_val: int | None,
) -> None:
    if add_val is not None:
        validate_non_negative_int(add_val, validate_name)
        setattr(task, field, (getattr(task, field) or 0) + add_val)
    elif usage_val is not None:
        setattr(task, field, (getattr(task, field) or 0) + usage_val)
    elif auto_val is not None:
        setattr(task, field, auto_val)


def _apply_total_tokens_update(
    task: GoalRecord,
    tokens_set: int | None,
    tokens_add: int | None,
    usage_total_tokens: int | None,
    auto_total_tokens: int | None,
) -> None:
    if tokens_set is not None:
        validate_non_negative_int(tokens_set, "tokens")
        task.tokens_total = tokens_set
    elif tokens_add is not None:
        validate_non_negative_int(tokens_add, "tokens_add")
        task.tokens_total = (task.tokens_total or 0) + tokens_add
    elif usage_total_tokens is not None:
        task.tokens_total = (task.tokens_total or 0) + usage_total_tokens
    elif auto_total_tokens is not None:
        task.tokens_total = auto_total_tokens


def _apply_model_update(
    task: GoalRecord,
    usage_model: str | None,
    model: str | None,
    auto_model: str | None,
) -> None:
    if usage_model is not None:
        validate_model_name(usage_model)
        task.model = usage_model
    elif model is not None:
        validate_model_name(model)
        task.model = model
    elif auto_model is not None:
        validate_model_name(auto_model)
        task.model = auto_model


def apply_goal_updates(
    entries: list[dict[str, Any]],
    task: GoalRecord,
    manual: ManualGoalUpdates,
    resolution: GoalUsageResolution = EMPTY_GOAL_USAGE_RESOLUTION,
) -> None:
    """Apply a CLI-driven update request to *task* in place.

    Precedence for cost/token/model fields: manual > usage-pricing > auto-recovery.
    `manual` carries user-facing flags; `resolution` carries the usage/auto
    recovery outputs produced by :func:`runtime_facade.resolve_goal_usage_updates`.
    """
    if manual.title is not None:
        if not manual.title.strip():
            raise ValueError("title cannot be empty")
        task.title = manual.title
    if manual.task_type is not None:
        validate_task_type(manual.task_type)
        ensure_goal_type_update_allowed(entries, task, manual.task_type)
        task.goal_type = manual.task_type
    if manual.status is not None:
        validate_status(manual.status)
        task.status = manual.status
    if manual.attempts_abs is not None:
        validate_non_negative_int(manual.attempts_abs, "attempts")
        task.attempts = manual.attempts_abs
    if manual.attempts_delta is not None:
        validate_non_negative_int(manual.attempts_delta, "attempts_delta")
        task.attempts = task.attempts + manual.attempts_delta

    _apply_cost_update(
        task, manual.cost_usd_set, manual.cost_usd_add,
        resolution.usage_cost_usd, resolution.auto_cost_usd,
    )
    _apply_int_token_update(
        task, "input_tokens", "input_tokens_add",
        add_val=manual.input_tokens_add,
        usage_val=resolution.usage_input_tokens,
        auto_val=resolution.auto_input_tokens,
    )
    _apply_int_token_update(
        task, "cached_input_tokens", "cached_input_tokens_add",
        add_val=manual.cached_input_tokens_add,
        usage_val=resolution.usage_cached_input_tokens,
        auto_val=resolution.auto_cached_input_tokens,
    )
    _apply_int_token_update(
        task, "output_tokens", "output_tokens_add",
        add_val=manual.output_tokens_add,
        usage_val=resolution.usage_output_tokens,
        auto_val=resolution.auto_output_tokens,
    )
    _apply_total_tokens_update(
        task, manual.tokens_set, manual.tokens_add,
        resolution.usage_total_tokens, resolution.auto_total_tokens,
    )
    _apply_model_update(task, resolution.usage_model, manual.model, resolution.auto_model)

    effective_agent_name = manual.agent_name or resolution.detected_agent_name
    if manual.failure_reason is not None:
        validate_failure_reason(manual.failure_reason)
        task.failure_reason = manual.failure_reason
    if manual.result_fit is not None:
        validate_result_fit(manual.result_fit)
        task.result_fit = manual.result_fit
    if effective_agent_name is not None:
        validate_agent_name(effective_agent_name)
        task.agent_name = effective_agent_name
    if manual.notes is not None:
        task.notes = manual.notes
    if manual.started_at is not None:
        task.started_at = parse_iso_datetime_flexible(manual.started_at, "started_at")
    if manual.finished_at is not None:
        task.finished_at = parse_iso_datetime_flexible(manual.finished_at, "finished_at")


def _needs_goal_window_nudge(task: GoalRecord) -> bool:
    """True when a closed product goal has a zero-duration window and no usage.

    The caller widens `started_at` by one second so the window covers the real
    work and automatic usage recovery has a non-empty interval to look at.
    """
    return (
        task.goal_type == "product"
        and task.status in {"success", "fail"}
        and task.cost_usd is None
        and task.tokens_total is None
        and task.started_at is not None
        and task.finished_at is not None
        and task.started_at == task.finished_at
    )


def finalize_goal_update(task: GoalRecord) -> None:
    if task.status in {"success", "fail"} and task.attempts == 0:
        task.attempts = 1
    if task.status in {"success", "fail"} and not task.finished_at:
        finished_dt = now_utc_datetime()
        if task.started_at is not None and finished_dt < task.started_at:
            finished_dt = task.started_at
        task.finished_at = finished_dt
    if _needs_goal_window_nudge(task) and task.started_at is not None:
        task.started_at = task.started_at - timedelta(seconds=1)
    if task.status == "success":
        task.failure_reason = None

    validate_goal_record(goal_to_dict(task))
