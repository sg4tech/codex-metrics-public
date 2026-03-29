from __future__ import annotations

from argparse import Namespace
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from codex_metrics.cost_audit import CostAuditReport
from codex_metrics.history_audit import AuditReport


class CommandRuntime(Protocol):
    def metrics_mutation_lock(self, metrics_path: Path) -> AbstractContextManager[Any]: ...
    def init_files(self, metrics_path: Path, report_path: Path, force: bool = False) -> None: ...
    def load_metrics(self, path: Path) -> dict[str, Any]: ...
    def recompute_summary(self, data: dict[str, Any]) -> None: ...
    def print_summary(self, data: dict[str, Any]) -> None: ...
    def sync_codex_usage(
        self,
        data: dict[str, Any],
        cwd: Path,
        pricing_path: Path,
        codex_state_path: Path,
        codex_logs_path: Path,
        codex_thread_id: str | None,
    ) -> int: ...
    def save_metrics(self, path: Path, data: dict[str, Any]) -> None: ...
    def save_report(self, path: Path, data: dict[str, Any]) -> None: ...
    def audit_history(self, data: dict[str, Any]) -> AuditReport: ...
    def render_audit_report(self, report: AuditReport) -> str: ...
    def audit_cost_coverage(
        self,
        data: dict[str, Any],
        *,
        pricing_path: Path,
        codex_state_path: Path,
        codex_logs_path: Path,
        codex_thread_id: str | None,
        cwd: Path,
    ) -> CostAuditReport: ...
    def render_cost_audit_report(self, report: CostAuditReport) -> str: ...
    def merge_tasks(self, data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]: ...
    def get_task(self, tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None: ...
    def upsert_task(
        self,
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
    ) -> dict[str, Any]: ...
    def sync_goal_attempt_entries(
        self,
        data: dict[str, Any],
        goal: dict[str, Any],
        previous_goal: dict[str, Any] | None,
    ) -> None: ...


def handle_init(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        cli_module.init_files(metrics_path, report_path, force=args.force)
    print(f"Initialized {metrics_path} and {report_path}")
    return 0


def handle_show(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    data = cli_module.load_metrics(metrics_path)
    cli_module.recompute_summary(data)
    cli_module.print_summary(data)
    return 0


def handle_audit_history(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.audit_history(data)
    print(cli_module.render_audit_report(report))
    return 0


def handle_audit_cost_coverage(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    pricing_path = Path(args.pricing_path)
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.audit_cost_coverage(
        data,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        codex_thread_id=args.codex_thread_id,
        cwd=Path.cwd(),
    )
    print(cli_module.render_cost_audit_report(report))
    return 0


def handle_sync_codex_usage(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    pricing_path = Path(args.pricing_path)
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        updated_tasks = cli_module.sync_codex_usage(
            data=data,
            cwd=Path.cwd(),
            pricing_path=pricing_path,
            codex_state_path=codex_state_path,
            codex_logs_path=codex_logs_path,
            codex_thread_id=args.codex_thread_id,
        )
        cli_module.recompute_summary(data)
        cli_module.save_metrics(metrics_path, data)
        cli_module.save_report(report_path, data)
    print(f"Synchronized Codex usage for {updated_tasks} task(s)")
    cli_module.print_summary(data)
    return 0


def handle_merge_tasks(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        task = cli_module.merge_tasks(
            data=data,
            keep_task_id=args.keep_task_id,
            drop_task_id=args.drop_task_id,
        )
        cli_module.recompute_summary(data)
        cli_module.save_metrics(metrics_path, data)
        cli_module.save_report(report_path, data)
    print(f"Merged goal {args.drop_task_id} into {args.keep_task_id}")
    print(f"Status: {task['status']}")
    print(f"Attempts: {task['attempts']}")
    cli_module.print_summary(data)
    return 0


def handle_update(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    pricing_path = Path(args.pricing_path)
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        previous_task = None
        existing_task = None
        if args.task_id is not None:
            existing_task = cli_module.get_task(data["goals"], args.task_id)
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
        )

        cli_module.sync_goal_attempt_entries(data, task, previous_task)
        cli_module.recompute_summary(data)
        cli_module.save_metrics(metrics_path, data)
        cli_module.save_report(report_path, data)

    print(f"Updated goal {task['goal_id']}")
    print(f"Status: {task['status']}")
    print(f"Attempts: {task['attempts']}")
    cli_module.print_summary(data)
    return 0
