from __future__ import annotations

import os
import shutil
import stat
import sys
from argparse import Namespace
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from codex_metrics.cost_audit import CostAuditReport
from codex_metrics.history_audit import AuditReport
from codex_metrics.history_compare import HistoryCompareReport
from codex_metrics.observability import (
    record_goal_merge_observation,
    record_goal_mutation_observation,
    record_usage_sync_observation,
)
from codex_metrics.retro_timeline import RetroTimelineReport
from codex_metrics.workflow_fsm import (
    WorkflowEvent,
)


class CommandRuntime(Protocol):
    def metrics_mutation_lock(self, metrics_path: Path) -> AbstractContextManager[Any]: ...
    def init_files(self, metrics_path: Path, report_path: Path | None, force: bool = False) -> None: ...
    def bootstrap_project(
        self,
        *,
        target_dir: Path,
        metrics_path: Path,
        report_path: Path | None,
        policy_path: Path,
        command_path: Path,
        agents_path: Path,
        force: bool = False,
        dry_run: bool = False,
    ) -> list[str]: ...
    def load_metrics(self, path: Path) -> dict[str, Any]: ...
    def recompute_summary(self, data: dict[str, Any]) -> None: ...
    def print_summary(self, data: dict[str, Any]) -> None: ...
    def sync_usage(
        self,
        data: dict[str, Any],
        cwd: Path,
        pricing_path: Path,
        usage_state_path: Path,
        usage_logs_path: Path,
        usage_thread_id: str | None,
        usage_backend: str | None = None,
    ) -> int: ...
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
    def detect_started_work(self, cwd: Path) -> Any: ...
    def ensure_active_task(self, data: dict[str, Any], cwd: Path) -> Any: ...
    def get_active_goals(self, data: dict[str, Any]) -> list[dict[str, Any]]: ...
    def resolve_workflow_resolution(self, data: dict[str, Any], cwd: Path, event: WorkflowEvent) -> Any: ...
    def audit_history(self, data: dict[str, Any]) -> AuditReport: ...
    def compare_metrics_to_history(self, data: dict[str, Any], *, warehouse_path: Path, cwd: Path, metrics_path: Path) -> HistoryCompareReport: ...
    def derive_retro_timeline(
        self,
        data: dict[str, Any],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
        window_size: int,
    ) -> RetroTimelineReport: ...
    def ingest_codex_history(self, source_root: Path, warehouse_path: Path) -> Any: ...
    def normalize_codex_history(self, warehouse_path: Path) -> Any: ...
    def derive_codex_history(self, warehouse_path: Path) -> Any: ...
    def verify_public_boundary(self, *, repo_root: Path, rules_path: Path) -> Any: ...
    def render_audit_report(self, report: AuditReport) -> str: ...
    def render_audit_report_json(self, report: AuditReport) -> str: ...
    def render_history_compare_report(self, report: HistoryCompareReport) -> str: ...
    def render_history_compare_report_json(self, report: HistoryCompareReport) -> str: ...
    def render_retro_timeline_report(self, report: RetroTimelineReport) -> str: ...
    def render_public_boundary_report(self, report: Any) -> str: ...
    def render_public_boundary_report_json(self, report: Any) -> str: ...
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


def _resolve_invocation_path() -> Path:
    argv0 = Path(sys.argv[0])
    if argv0.is_absolute() or argv0.parent != Path("."):
        return argv0.resolve()

    discovered = shutil.which(sys.argv[0])
    if discovered is not None:
        return Path(discovered).resolve()

    return argv0.resolve()


def _path_dir_is_available(target_dir: Path) -> bool:
    normalized_target = target_dir.expanduser().resolve(strict=False)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        if Path(entry).expanduser().resolve(strict=False) == normalized_target:
            return True
    return False


def _shell_path_snippet(target_dir: Path) -> tuple[str, str]:
    shell_name = Path(os.environ.get("SHELL", "")).name
    rendered_dir = str(target_dir.expanduser())
    export_line = f'export PATH="{rendered_dir}:$PATH"'
    if shell_name == "zsh":
        return "~/.zshrc", export_line
    if shell_name == "bash":
        return "~/.bashrc", export_line
    return "your shell profile", export_line


def _shell_profile_path() -> Path | None:
    shell_name = Path(os.environ.get("SHELL", "")).name
    home = Path.home()
    if shell_name == "zsh":
        return home / ".zshrc"
    if shell_name == "bash":
        return home / ".bashrc"
    return None


def _ensure_profile_has_path_line(profile_path: Path, export_line: str) -> bool:
    if profile_path.exists():
        existing_text = profile_path.read_text(encoding="utf-8")
    else:
        existing_text = ""
    if export_line in existing_text:
        return False

    updated = existing_text.rstrip("\n")
    if updated:
        updated += "\n"
    updated += f"{export_line}\n"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(updated, encoding="utf-8")
    return True


def _detect_shadowing_command(*, command_name: str, target_path: Path) -> Path | None:
    resolved_on_path = shutil.which(command_name)
    if resolved_on_path is None:
        return None

    resolved_path = Path(resolved_on_path).expanduser().resolve(strict=False)
    if resolved_path == target_path.expanduser().resolve(strict=False):
        return None

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env is None:
        return None

    venv_path = Path(virtual_env).expanduser().resolve(strict=False)
    try:
        resolved_path.relative_to(venv_path)
    except ValueError:
        return None
    return resolved_path


def _write_python_launcher(target_path: Path, *, python_executable: Path, source_path: Path) -> None:
    launcher = (
        "#!/bin/sh\n"
        f"exec '{python_executable}' '{source_path}' \"$@\"\n"
    )
    target_path.write_text(launcher, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_source_module_launcher(target_path: Path, *, python_executable: Path, source_root: Path) -> None:
    launcher = (
        "#!/bin/sh\n"
        "if [ -n \"$PYTHONPATH\" ]; then\n"
        f"  export PYTHONPATH='{source_root}':\"$PYTHONPATH\"\n"
        "else\n"
        f"  export PYTHONPATH='{source_root}'\n"
        "fi\n"
        f"exec '{python_executable}' -m codex_metrics \"$@\"\n"
    )
    target_path.write_text(launcher, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _render_python_launcher(*, python_executable: Path, source_path: Path, repo_root: Path) -> str:
    return (
        "#!/bin/sh\n"
        f"cd '{repo_root}' || exit 1\n"
        f"exec '{python_executable}' '{source_path}' \"$@\"\n"
    )


def _render_source_module_launcher(*, python_executable: Path, source_root: Path, repo_root: Path) -> str:
    return (
        "#!/bin/sh\n"
        f"cd '{repo_root}' || exit 1\n"
        "if [ -n \"$PYTHONPATH\" ]; then\n"
        f"  export PYTHONPATH='{source_root}':\"$PYTHONPATH\"\n"
        "else\n"
        f"  export PYTHONPATH='{source_root}'\n"
        "fi\n"
        f"exec '{python_executable}' -m codex_metrics \"$@\"\n"
    )


def _render_repo_local_wrapper(source_path: Path, repo_root: Path) -> str:
    if source_path.suffix == ".py" and source_path.name == "__main__.py":
        return _render_source_module_launcher(
            python_executable=Path(sys.executable),
            source_root=source_path.parents[1],
            repo_root=repo_root,
        )
    if source_path.suffix == ".py":
        return _render_python_launcher(
            python_executable=Path(sys.executable),
            source_path=source_path,
            repo_root=repo_root,
        )
    return "#!/bin/sh\n" f"cd '{repo_root}' || exit 1\n" f"exec '{source_path}' \"$@\"\n"


def _write_repo_local_wrapper(target_path: Path, source_path: Path, repo_root: Path) -> str:
    content = _render_repo_local_wrapper(source_path, repo_root)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return content


def handle_install_self(args: Namespace, _cli_module: CommandRuntime) -> int:
    source_path = _resolve_invocation_path()
    target_path = Path(args.target_path) if args.target_path else Path(args.target_dir) / args.command_name

    if source_path == target_path.resolve(strict=False):
        print(f"Already installed at {target_path}")
        shadowing_path = _detect_shadowing_command(command_name=args.command_name, target_path=target_path)
        if shadowing_path is not None:
            print(
                f"Warning: active virtualenv is shadowing the global install via {shadowing_path}. "
                f"Use {target_path} explicitly or deactivate the virtualenv before relying on `{args.command_name}`."
            )
        return 0

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() or target_path.is_symlink():
        if target_path.is_dir() and not target_path.is_symlink():
            raise ValueError(f"Install target is a directory: {target_path}")
        target_path.unlink()

    launcher_mode = source_path.suffix == ".py" and os.name != "nt"
    use_copy = (args.copy or os.name == "nt") and not launcher_mode
    if launcher_mode and source_path.name == "__main__.py":
        _write_source_module_launcher(
            target_path,
            python_executable=Path(sys.executable),
            source_root=source_path.parents[1],
        )
        verb = "Installed launcher"
    elif launcher_mode:
        _write_python_launcher(target_path, python_executable=Path(sys.executable), source_path=source_path)
        verb = "Installed launcher"
    elif use_copy:
        shutil.copy2(source_path, target_path)
        mode = source_path.stat().st_mode
        target_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        verb = "Copied"
    else:
        target_path.symlink_to(source_path)
        verb = "Linked"

    print(f"{verb} {source_path} -> {target_path}")
    if not _path_dir_is_available(target_path.parent):
        profile_name, export_line = _shell_path_snippet(target_path.parent)
        profile_path = _shell_profile_path()
        if args.write_shell_profile:
            if profile_path is None:
                raise ValueError("Cannot determine shell profile automatically for this shell; add PATH manually.")
            changed = _ensure_profile_has_path_line(profile_path, export_line)
            if changed:
                print(f"Added PATH update to {profile_path}")
            else:
                print(f"PATH update already present in {profile_path}")
        else:
            print(f"Warning: {target_path.parent.expanduser()} is not on PATH.")
            print(f"Add this line to {profile_name}:")
            print(export_line)
        print("Then reopen your shell before running `codex-metrics` by command name.")
    shadowing_path = _detect_shadowing_command(command_name=args.command_name, target_path=target_path)
    if shadowing_path is not None:
        print(
            f"Warning: active virtualenv is shadowing the global install via {shadowing_path}. "
            f"Use {target_path} explicitly or deactivate the virtualenv before relying on `{args.command_name}`."
        )
    return 0


def handle_init(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    with cli_module.metrics_mutation_lock(metrics_path):
        cli_module.init_files(metrics_path, report_path, force=args.force)
    print(f"Initialized {metrics_path}")
    if report_path is not None:
        print(f"Rendered markdown report: {report_path}")
    return 0


def handle_bootstrap(args: Namespace, cli_module: CommandRuntime) -> int:
    target_dir = Path(args.target_dir)

    def resolve_target_path(raw_path: str) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else target_dir / path

    metrics_path = resolve_target_path(args.metrics_path)
    report_path = resolve_target_path(args.report_path) if getattr(args, "write_report", False) else None
    policy_path = resolve_target_path(args.policy_path)
    command_path = resolve_target_path(args.command_path)
    agents_path = resolve_target_path(args.agents_path)
    source_path = _resolve_invocation_path()
    wrapper_content = _render_repo_local_wrapper(source_path, target_dir.resolve())
    wrapper_exists = command_path.exists()
    wrapper_matches = wrapper_exists and command_path.read_text(encoding="utf-8") == wrapper_content

    with cli_module.metrics_mutation_lock(metrics_path):
        messages = cli_module.bootstrap_project(
            target_dir=target_dir,
            metrics_path=metrics_path,
            report_path=report_path,
            policy_path=policy_path,
            command_path=command_path,
            agents_path=agents_path,
            force=args.force,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            if not wrapper_exists:
                messages.append(f"Would create command wrapper: {command_path}")
            elif wrapper_matches:
                messages.append(f"Would keep command wrapper: {command_path}")
            else:
                messages.append(f"Would update command wrapper: {command_path}")
        else:
            if not wrapper_exists:
                _write_repo_local_wrapper(command_path, source_path, target_dir.resolve())
                messages.append(f"Created command wrapper: {command_path}")
            elif wrapper_matches:
                messages.append(f"Keeping command wrapper: {command_path}")
            else:
                _write_repo_local_wrapper(command_path, source_path, target_dir.resolve())
                messages.append(f"Updated command wrapper: {command_path}")

    for message in messages:
        print(message)
    return 0


def handle_show(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    data = cli_module.load_metrics(metrics_path)
    cli_module.recompute_summary(data)
    warning = None
    resolution = cli_module.resolve_workflow_resolution(data, Path.cwd(), WorkflowEvent.SHOW)
    if resolution.decision.action == "warning":
        warning = f"Warning: {resolution.decision.message}."
    if warning is not None:
        print(warning)
    cli_module.print_summary(data)
    return 0


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


def handle_ensure_active_task(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        resolution = cli_module.ensure_active_task(data, Path.cwd())
        if resolution.status == "created":
            cli_module.recompute_summary(data)
            cli_module.save_metrics(metrics_path, data)
    print(resolution.message)
    return 0


def handle_audit_history(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.audit_history(data)
    if getattr(args, "json", False):
        print(cli_module.render_audit_report_json(report))
    else:
        print(cli_module.render_audit_report(report))
    return 0


def handle_compare_metrics_to_history(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    warehouse_path = Path(args.warehouse_path).expanduser()
    cwd = Path(args.cwd).expanduser()
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.compare_metrics_to_history(
        data,
        warehouse_path=warehouse_path,
        cwd=cwd,
        metrics_path=metrics_path,
    )
    if getattr(args, "json", False):
        print(cli_module.render_history_compare_report_json(report))
    else:
        print(cli_module.render_history_compare_report(report))
    return 0


def handle_ingest_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    source_root = Path(args.source_root).expanduser()
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.ingest_codex_history(source_root, warehouse_path)
    print(f"Ingested Codex history into {summary.warehouse_path}")
    print(f"Source root: {summary.source_root}")
    print(f"Scanned files: {summary.scanned_files}")
    print(f"Imported files: {summary.imported_files}")
    print(f"Skipped files: {summary.skipped_files}")
    print(f"Projects: {summary.projects}")
    print(f"Threads: {summary.threads}")
    print(f"Sessions: {summary.sessions}")
    print(f"Session events: {summary.session_events}")
    print(f"Token count events: {summary.token_count_events}")
    print(f"Token usage events: {summary.token_usage_events}")
    print(f"Input tokens: {summary.input_tokens}")
    print(f"Cached input tokens: {summary.cached_input_tokens}")
    print(f"Output tokens: {summary.output_tokens}")
    print(f"Reasoning output tokens: {summary.reasoning_output_tokens}")
    print(f"Total tokens: {summary.total_tokens}")
    print(f"Messages: {summary.messages}")
    print(f"Logs: {summary.logs}")
    return 0


def handle_normalize_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.normalize_codex_history(warehouse_path)
    print(f"Normalized Codex history in {summary.warehouse_path}")
    print(f"Projects: {summary.projects}")
    print(f"Threads: {summary.threads}")
    print(f"Sessions: {summary.sessions}")
    print(f"Messages: {summary.messages}")
    print(f"Usage events: {summary.usage_events}")
    print(f"Logs: {summary.logs}")
    return 0


def handle_derive_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.derive_codex_history(warehouse_path)
    print(f"Derived Codex history in {summary.warehouse_path}")
    print(f"Projects: {summary.projects}")
    print(f"Goals: {summary.goals}")
    print(f"Attempts: {summary.attempts}")
    print(f"Timeline events: {summary.timeline_events}")
    print(f"Retry chains: {summary.retry_chains}")
    print(f"Message facts: {summary.message_facts}")
    print(f"Session usage: {summary.session_usage}")
    return 0


def handle_derive_retro_timeline(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    warehouse_path = Path(args.warehouse_path).expanduser()
    cwd = Path(args.cwd).expanduser()
    data = cli_module.load_metrics(metrics_path)
    cli_module.recompute_summary(data)
    with cli_module.metrics_mutation_lock(warehouse_path):
        report = cli_module.derive_retro_timeline(
            data,
            warehouse_path=warehouse_path,
            cwd=cwd,
            metrics_path=metrics_path,
            window_size=args.window_size,
        )
    print(cli_module.render_retro_timeline_report(report))
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


def handle_verify_public_boundary(args: Namespace, cli_module: CommandRuntime) -> int:
    report = cli_module.verify_public_boundary(
        repo_root=Path(args.repo_root).expanduser(),
        rules_path=Path(args.rules_path).expanduser(),
    )
    if getattr(args, "json", False):
        print(cli_module.render_public_boundary_report_json(report))
    else:
        print(cli_module.render_public_boundary_report(report))
    return 0 if not report.findings else 1


def handle_sync_codex_usage(args: Namespace, cli_module: CommandRuntime) -> int:
    return handle_sync_usage(args, cli_module)


def handle_sync_usage(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    pricing_path = Path(args.pricing_path)
    usage_state_path = Path(args.usage_state_path)
    usage_logs_path = Path(args.usage_logs_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        updated_tasks = cli_module.sync_usage(
            data=data,
            cwd=Path.cwd(),
            pricing_path=pricing_path,
            usage_state_path=usage_state_path,
            usage_logs_path=usage_logs_path,
            usage_thread_id=args.usage_thread_id,
            usage_backend=getattr(args, "usage_backend", None),
        )
        cli_module.recompute_summary(data)
        cli_module.save_metrics(metrics_path, data)
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
    cli_module.print_summary(data)
    return 0


def handle_merge_tasks(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        task = cli_module.merge_tasks(
            data=data,
            keep_task_id=args.keep_task_id,
            drop_task_id=args.drop_task_id,
        )
        cli_module.recompute_summary(data)
        cli_module.save_metrics(metrics_path, data)
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
    cli_module.print_summary(data)
    return 0


def handle_update(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path) if getattr(args, "write_report", False) else None
    pricing_path = Path(args.pricing_path)
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        data = cli_module.load_metrics(metrics_path)
        if args.task_id is not None and _command_requires_active_goal(args):
            _require_active_goal_for_existing_mutation(cli_module, Path.cwd(), data)
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
    cli_module.print_summary(data)
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


def handle_render_report(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    data = cli_module.load_metrics(metrics_path)
    cli_module.recompute_summary(data)
    cli_module.save_report(report_path, data)
    print(f"Rendered markdown report: {report_path}")
    return 0
