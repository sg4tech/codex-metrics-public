"""CLI handlers for goal mutation: update, merge, start, continue, finish."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.commands._runtime import _command_to_event_type
from ai_agents_metrics.domain import (
    get_goal_entries,
    get_task,
    load_metrics,
    recompute_summary,
    sync_goal_attempt_entries,
)
from ai_agents_metrics.event_store import append_event
from ai_agents_metrics.observability import (
    record_goal_merge_observation,
    record_goal_mutation_observation,
)
from ai_agents_metrics.reporting import print_summary
from ai_agents_metrics.storage import metrics_mutation_lock
from ai_agents_metrics.workflow_fsm import WorkflowEvent

if TYPE_CHECKING:
    from ai_agents_metrics.commands._runtime import CommandRuntime


def _command_requires_active_goal(args: Namespace) -> bool:
    if args.command == "continue-task":
        return True
    if args.command == "finish-task":
        return False
    if args.command == "update":
        return getattr(args, "status", None) in {None, "in_progress"}
    return False


def _require_active_goal_for_existing_mutation(cli_module: CommandRuntime, cwd: Path, data: dict[str, Any]) -> None:
    active_goals = cli_module.get_active_goals(data)
    if active_goals:
        return

    resolution = cli_module.resolve_workflow_resolution(data, cwd, WorkflowEvent.CONTINUE_TASK)
    if resolution.decision.action == "block":
        raise ValueError(resolution.decision.message)


def handle_merge_tasks(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    with metrics_mutation_lock(metrics_path):
        data = load_metrics(metrics_path)
        goals_snapshot = {g["goal_id"]: dict(g) for g in data["goals"]}
        task = cli_module.merge_tasks(
            data=data,
            keep_task_id=args.keep_task_id,
            drop_task_id=args.drop_task_id,
        )
        kept_entries = get_goal_entries(data["entries"], args.keep_task_id)
        # Capture any downstream goals whose supersession link was rewritten
        relinked_goals = [
            g for g in data["goals"]
            if g["goal_id"] != args.keep_task_id and g != goals_snapshot.get(g["goal_id"], {})
        ]
        append_event(
            metrics_path,
            "goals_merged",
            goal=task,
            entries=kept_entries,
            dropped_goal_id=args.drop_task_id,
            goals=relinked_goals or None,
        )
        recompute_summary(data)
        record_goal_merge_observation(
            metrics_path,
            command="merge-tasks",
            keep_task_id=args.keep_task_id,
            drop_task_id=args.drop_task_id,
            merged_task=task,
        )
        if report_path is not None:
            cli_module.save_report(report_path, data)
    print(f"Merged goal {args.drop_task_id} into {args.keep_task_id}")
    print(f"Status: {task['status']}")
    print(f"Attempts: {task['attempts']}")
    print_summary(data)
    return 0


def handle_update(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    pricing_path = cli_module.resolve_effective_pricing_path(
        cwd=Path.cwd(),
        pricing_path=Path(args.pricing_path) if args.pricing_path else None,
    )
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    claude_root = Path(args.claude_root) if getattr(args, "claude_root", None) is not None else Path.home() / ".claude"
    with metrics_mutation_lock(metrics_path):
        data = load_metrics(metrics_path)
        if args.task_id is not None and _command_requires_active_goal(args):
            _require_active_goal_for_existing_mutation(cli_module, Path.cwd(), data)
        previous_task = None
        existing_task = None
        if args.task_id is not None:
            existing_task = get_task(data["goals"], args.task_id)
        if existing_task is not None:
            previous_task = dict(existing_task)

        task = cli_module.upsert_task(
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
            result_fit=args.result_fit,
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
            claude_root=claude_root,
        )

        sync_goal_attempt_entries(data, task, previous_task)
        goal_entries = get_goal_entries(data["entries"], task["goal_id"])
        append_event(
            metrics_path,
            _command_to_event_type(getattr(args, "command", None)),
            goal=task,
            entries=goal_entries,
        )
        recompute_summary(data)
        record_goal_mutation_observation(
            metrics_path,
            command=getattr(args, "command", "update"),
            previous_task=previous_task,
            current_task=task,
        )
        if report_path is not None:
            cli_module.save_report(report_path, data)

    print(f"Updated goal {task['goal_id']}")
    print(f"Status: {task['status']}")
    print(f"Attempts: {task['attempts']}")
    print_summary(data)
    return 0


def _build_update_namespace(args: Namespace, **overrides: Any) -> Namespace:
    values = {
        "command": getattr(args, "command", None),
        "task_id": None,
        "title": None,
        "task_type": None,
        "continuation_of": None,
        "supersedes_task_id": None,
        "status": None,
        "attempts_delta": None,
        "attempts": None,
        "cost_usd_add": None,
        "cost_usd": None,
        "tokens_add": None,
        "tokens": None,
        "failure_reason": None,
        "result_fit": None,
        "notes": None,
        "started_at": None,
        "finished_at": None,
        "model": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "pricing_path": getattr(args, "pricing_path", None),
        "codex_state_path": getattr(args, "codex_state_path", None),
        "codex_logs_path": getattr(args, "codex_logs_path", None),
        "codex_thread_id": getattr(args, "codex_thread_id", None),
        "claude_root": getattr(args, "claude_root", None),
        "metrics_path": getattr(args, "metrics_path", None),
        "report_path": getattr(args, "report_path", None),
        "write_report": getattr(args, "write_report", False),
    }
    values.update(overrides)
    return Namespace(**values)


def handle_start_task(args: Namespace, cli_module: CommandRuntime) -> int:
    update_args = _build_update_namespace(
        args,
        command="start-task",
        title=args.title,
        task_type=args.task_type,
        continuation_of=args.continuation_of,
        supersedes_task_id=args.supersedes_task_id,
        attempts_delta=1,
        notes=args.notes,
        started_at=args.started_at,
        model=args.model,
        input_tokens=args.input_tokens,
        cached_input_tokens=args.cached_input_tokens,
        output_tokens=args.output_tokens,
        cost_usd_add=args.cost_usd_add,
        tokens_add=args.tokens_add,
    )
    return handle_update(update_args, cli_module)


def handle_continue_task(args: Namespace, cli_module: CommandRuntime) -> int:
    update_args = _build_update_namespace(
        args,
        command="continue-task",
        task_id=args.task_id,
        attempts_delta=1,
        notes=args.notes,
        failure_reason=args.failure_reason,
        started_at=args.started_at,
        model=args.model,
        input_tokens=args.input_tokens,
        cached_input_tokens=args.cached_input_tokens,
        output_tokens=args.output_tokens,
        cost_usd_add=args.cost_usd_add,
        tokens_add=args.tokens_add,
    )
    return handle_update(update_args, cli_module)


def handle_finish_task(args: Namespace, cli_module: CommandRuntime) -> int:
    update_args = _build_update_namespace(
        args,
        command="finish-task",
        task_id=args.task_id,
        status=args.status,
        failure_reason=args.failure_reason,
        result_fit=args.result_fit,
        notes=args.notes,
        finished_at=args.finished_at,
        model=args.model,
        input_tokens=args.input_tokens,
        cached_input_tokens=args.cached_input_tokens,
        output_tokens=args.output_tokens,
        cost_usd_add=args.cost_usd_add,
        tokens_add=args.tokens_add,
    )
    return handle_update(update_args, cli_module)
