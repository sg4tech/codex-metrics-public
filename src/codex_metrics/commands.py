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


class CommandRuntime(Protocol):
    def metrics_mutation_lock(self, metrics_path: Path) -> AbstractContextManager[Any]: ...
    def init_files(self, metrics_path: Path, report_path: Path, force: bool = False) -> None: ...
    def bootstrap_project(
        self,
        *,
        target_dir: Path,
        metrics_path: Path,
        report_path: Path,
        policy_path: Path,
        agents_path: Path,
        force: bool = False,
        dry_run: bool = False,
    ) -> list[str]: ...
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


def handle_install_self(args: Namespace, _cli_module: CommandRuntime) -> int:
    source_path = _resolve_invocation_path()
    target_path = Path(args.target_path) if args.target_path else Path(args.target_dir) / args.command_name

    if source_path == target_path.resolve(strict=False):
        print(f"Already installed at {target_path}")
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
    return 0


def handle_init(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    with cli_module.metrics_mutation_lock(metrics_path):
        cli_module.init_files(metrics_path, report_path, force=args.force)
    print(f"Initialized {metrics_path} and {report_path}")
    return 0


def handle_bootstrap(args: Namespace, cli_module: CommandRuntime) -> int:
    target_dir = Path(args.target_dir)

    def resolve_target_path(raw_path: str) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else target_dir / path

    metrics_path = resolve_target_path(args.metrics_path)
    report_path = resolve_target_path(args.report_path)
    policy_path = resolve_target_path(args.policy_path)
    agents_path = resolve_target_path(args.agents_path)

    with cli_module.metrics_mutation_lock(metrics_path):
        messages = cli_module.bootstrap_project(
            target_dir=target_dir,
            metrics_path=metrics_path,
            report_path=report_path,
            policy_path=policy_path,
            agents_path=agents_path,
            force=args.force,
            dry_run=args.dry_run,
        )

    for message in messages:
        print(message)
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
