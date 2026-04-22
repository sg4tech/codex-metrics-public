"""CLI handlers for show, ensure-active-task, sync-usage, and verify-public-boundary."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ai_agents_metrics.domain import (
    get_goal_entries,
    get_task,
    load_metrics,
    recompute_summary,
)
from ai_agents_metrics.event_store import append_event
from ai_agents_metrics.observability import record_usage_sync_observation
from ai_agents_metrics.public_boundary import (
    render_public_boundary_report,
    render_public_boundary_report_json,
)
from ai_agents_metrics.reporting import print_summary
from ai_agents_metrics.storage import metrics_mutation_lock
from ai_agents_metrics.workflow_fsm import WorkflowEvent

if TYPE_CHECKING:
    from argparse import Namespace

    from ai_agents_metrics.commands._runtime import CommandRuntime


def handle_show(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    _warehouse_raw = getattr(args, "warehouse_path", "")
    # Guard against the empty-string case: Path("").expanduser() resolves to Path(".")
    # which always exists and causes an unintended SQLite connect attempt.
    warehouse_path = Path(_warehouse_raw).expanduser() if _warehouse_raw else Path()
    data = cli_module.load_metrics(metrics_path)
    cli_module.recompute_summary(data)
    history_signals = cli_module.read_history_signals(warehouse_path, Path.cwd(), data)
    warning = None
    resolution = cli_module.resolve_workflow_resolution(data, Path.cwd(), WorkflowEvent.SHOW)
    if resolution.decision.action == "warning":
        warning = f"Warning: {resolution.decision.message}."
    if warning is not None:
        if getattr(args, "json", False):
            print(warning, file=sys.stderr)
        else:
            print(warning)
    if getattr(args, "json", False):
        print(cli_module.render_summary_json(data, history_signals))
    else:
        cli_module.print_summary(data, history_signals)
    return 0


def handle_ensure_active_task(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    with metrics_mutation_lock(metrics_path):
        data = load_metrics(metrics_path)
        resolution = cli_module.ensure_active_task(data, Path.cwd())
        if resolution.status == "created" and resolution.goal_id is not None:
            created_goal = get_task(data["goals"], resolution.goal_id)
            goal_entries = get_goal_entries(data["entries"], resolution.goal_id)
            append_event(metrics_path, "goal_started", goal=created_goal, entries=goal_entries)
    print(resolution.message)
    return 0


def handle_verify_public_boundary(args: Namespace, cli_module: CommandRuntime) -> int:
    report = cli_module.verify_public_boundary(
        repo_root=Path(args.repo_root).expanduser(),
        rules_path=Path(args.rules_path).expanduser(),
    )
    if getattr(args, "json", False):
        print(render_public_boundary_report_json(report))
    else:
        print(render_public_boundary_report(report))
    return 0 if not report.findings else 1


def handle_sync_codex_usage(args: Namespace, cli_module: CommandRuntime) -> int:
    return handle_sync_usage(args, cli_module)


def handle_sync_usage(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    pricing_path = cli_module.resolve_effective_pricing_path(
        cwd=Path.cwd(),
        pricing_path=Path(args.pricing_path) if args.pricing_path else None,
    )
    usage_state_path = Path(args.usage_state_path)
    usage_logs_path = Path(args.usage_logs_path)
    claude_root = Path(args.claude_root) if getattr(args, "claude_root", None) is not None else Path.home() / ".claude"
    with metrics_mutation_lock(metrics_path):
        data = load_metrics(metrics_path)
        snapshot_before = {goal["goal_id"]: dict(goal) for goal in data["goals"]}
        updated_tasks = cli_module.sync_usage(
            data=data,
            cwd=Path.cwd(),
            pricing_path=pricing_path,
            usage_state_path=usage_state_path,
            usage_logs_path=usage_logs_path,
            usage_thread_id=args.usage_thread_id,
            usage_backend=getattr(args, "usage_backend", None),
            claude_root=claude_root,
        )
        for goal in data["goals"]:
            if goal != snapshot_before.get(goal["goal_id"], {}):
                goal_entries = get_goal_entries(data["entries"], goal["goal_id"])
                append_event(metrics_path, "usage_synced", goal=goal, entries=goal_entries)
        recompute_summary(data)
        record_usage_sync_observation(
            metrics_path,
            command="sync-usage",
            updated_tasks=updated_tasks,
            usage_backend=getattr(args, "usage_backend", None),
            usage_thread_id=args.usage_thread_id,
        )
        if report_path is not None:
            cli_module.save_report(report_path, data)
    print(f"Synchronized usage for {updated_tasks} task(s)")
    print_summary(data)
    return 0
