"""Task mutation pipeline: upsert, sync usage, merge goals."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain import (
    ManualGoalUpdates,
    apply_goal_updates,
    build_merged_notes,
    choose_earliest_timestamp,
    choose_latest_timestamp,
    combine_optional_cost,
    combine_optional_tokens,
    create_goal_record,
    finalize_goal_update,
    get_task_index,
    goal_from_dict,
    goal_to_dict,
    next_goal_id,
    resolve_linked_task_reference,
    sync_goal_attempt_entries,
    validate_entry_record,
    validate_goal_record,
    validate_goal_supersession_graph,
)
from ai_agents_metrics.runtime_facade.costs import resolve_goal_usage_updates
from ai_agents_metrics.runtime_facade.orchestration import CLAUDE_ROOT
from ai_agents_metrics.usage_backends import (
    ClaudeUsageBackend,
    UsageBackend,
    select_usage_backend,
)
from ai_agents_metrics.usage_backends import (
    resolve_usage_window as resolve_backend_usage_window,
)

if TYPE_CHECKING:
    from pathlib import Path


# upsert_task is the central CLI-surface mutator; its kwargs mirror the
# `update`/`start-task`/`finish-task` argparse flags. See apply_goal_updates
# for the matching precedent and follow-up plan.
def upsert_task(  # pylint: disable=too-many-arguments,too-many-locals
    *,
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
    resolution = resolve_goal_usage_updates(
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
    apply_goal_updates(
        entries,
        task,
        ManualGoalUpdates(
            title=title,
            task_type=task_type,
            status=status,
            attempts_delta=attempts_delta,
            attempts_abs=attempts_abs,
            cost_usd_add=cost_usd_add,
            cost_usd_set=cost_usd_set,
            tokens_add=tokens_add,
            tokens_set=tokens_set,
            failure_reason=failure_reason,
            result_fit=result_fit,
            notes=notes,
            started_at=started_at,
            finished_at=finished_at,
            model=model,
        ),
        resolution,
    )
    finalize_goal_update(task)
    task_dict = goal_to_dict(task)
    tasks[task_index] = task_dict
    return task_dict


def _resolve_sync_usage_window(
    task: dict[str, Any],
    *,
    cwd: Path,
    pricing_path: Path,
    usage_state_path: Path,
    usage_logs_path: Path,
    usage_thread_id: str | None,
    usage_backend: UsageBackend | None,
    claude_root: Path,
) -> tuple[Any, str | None]:
    """Resolve the usage window for one task; return (window, detected_agent_name)."""
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
    return window, detected_agent_name


def _apply_auto_usage_updates(
    task: dict[str, Any], window: Any, detected_agent_name: str | None
) -> bool:
    """Copy resolved window fields onto *task*; return True if anything changed."""
    auto_fields: list[tuple[str, Any]] = [
        ("cost_usd", window.cost_usd),
        ("input_tokens", window.input_tokens),
        ("cached_input_tokens", window.cached_input_tokens),
        ("output_tokens", window.output_tokens),
        ("tokens_total", window.total_tokens),
        ("model", window.model_name),
    ]
    if all(value is None for _, value in auto_fields):
        return False
    changed = False
    for field_name, value in auto_fields:
        if value is not None and task.get(field_name) != value:
            task[field_name] = value
            changed = True
    if detected_agent_name is not None and task.get("agent_name") is None:
        task["agent_name"] = detected_agent_name
        changed = True
    return changed


def sync_usage(
    data: dict[str, Any],
    *,
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
        window, detected_agent_name = _resolve_sync_usage_window(
            task,
            cwd=cwd,
            pricing_path=pricing_path,
            usage_state_path=usage_state_path,
            usage_logs_path=usage_logs_path,
            usage_thread_id=usage_thread_id,
            usage_backend=usage_backend,
            claude_root=claude_root,
        )
        if not _apply_auto_usage_updates(task, window, detected_agent_name):
            continue
        validate_goal_record(task)
        sync_goal_attempt_entries(data, task, previous_task)
        updated_tasks += 1
    return updated_tasks


def sync_codex_usage(
    data: dict[str, Any],
    *,
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


def _validate_merge_preconditions(
    tasks: list[dict[str, Any]],
    keep_task_id: str,
    drop_task_id: str,
) -> tuple[int, int, dict[str, Any], dict[str, Any]]:
    if keep_task_id == drop_task_id:
        raise ValueError("keep_task_id and drop_task_id must be different")
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
    return keep_index, drop_index, kept_task, dropped_task


def _verify_merge_supersession(
    tasks: list[dict[str, Any]],
    keep_task_id: str,
    drop_task_id: str,
) -> None:
    """Simulate the merge on a copy and validate the supersession graph stays acyclic."""
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


def _merge_kept_task_fields(kept_task: dict[str, Any], dropped_task: dict[str, Any]) -> None:
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


def _rehome_entries_and_resolve_model(
    data: dict[str, Any],
    kept_task: dict[str, Any],
    keep_task_id: str,
    drop_task_id: str,
) -> None:
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


def merge_tasks(data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = data["goals"]
    _, drop_index, kept_task, dropped_task = _validate_merge_preconditions(
        tasks, keep_task_id, drop_task_id
    )
    _verify_merge_supersession(tasks, keep_task_id, drop_task_id)
    _merge_kept_task_fields(kept_task, dropped_task)
    _rehome_entries_and_resolve_model(data, kept_task, keep_task_id, drop_task_id)
    validate_goal_record(kept_task)
    for task in tasks:
        if task.get("supersedes_goal_id") == drop_task_id:
            task["supersedes_goal_id"] = keep_task_id
            validate_goal_record(task)
    del tasks[drop_index]
    return kept_task
