from __future__ import annotations

import os
import shutil
import stat
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Protocol

from ai_agents_metrics.cost_audit import (
    CostAuditReport,
    render_cost_audit_report,
)
from ai_agents_metrics.domain import (
    get_goal_entries,
    get_task,
    load_metrics,
    recompute_summary,
    sync_goal_attempt_entries,
)
from ai_agents_metrics.event_store import append_event
from ai_agents_metrics.history.audit import (
    AuditReport,
)
from ai_agents_metrics.history.classify import ClassifySummary
from ai_agents_metrics.history.compare import (
    HistoryCompareReport,
    HistorySignals,
)
from ai_agents_metrics.history.derive import DeriveSummary
from ai_agents_metrics.history.ingest import IngestSummary, default_raw_warehouse_path
from ai_agents_metrics.history.normalize import NormalizeSummary
from ai_agents_metrics.observability import (
    record_goal_merge_observation,
    record_goal_mutation_observation,
    record_usage_sync_observation,
)
from ai_agents_metrics.public_boundary import (
    render_public_boundary_report,
    render_public_boundary_report_json,
)
from ai_agents_metrics.reporting import print_summary
from ai_agents_metrics.retro_timeline import (
    RetroTimelineReport,
)
from ai_agents_metrics.storage import metrics_mutation_lock
from ai_agents_metrics.workflow_fsm import (
    WorkflowEvent,
)


class CommandRuntime(Protocol):
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
    def sync_usage(
        self,
        data: dict[str, Any],
        cwd: Path,
        pricing_path: Path,
        usage_state_path: Path,
        usage_logs_path: Path,
        usage_thread_id: str | None,
        usage_backend: str | None = None,
        claude_root: Path = ...,
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
    def save_report(self, path: Path, data: dict[str, Any]) -> None: ...
    def detect_started_work(self, cwd: Path) -> Any: ...
    def ensure_active_task(self, data: dict[str, Any], cwd: Path) -> Any: ...
    def get_active_goals(self, data: dict[str, Any]) -> list[dict[str, Any]]: ...
    def resolve_workflow_resolution(self, data: dict[str, Any], cwd: Path, event: WorkflowEvent) -> Any: ...
    def ingest_codex_history(self, source_root: Path, warehouse_path: Path, source: str = ...) -> Any: ...
    def normalize_codex_history(self, warehouse_path: Path) -> Any: ...
    def classify_codex_history(self, warehouse_path: Path) -> Any: ...
    def derive_codex_history(self, warehouse_path: Path) -> Any: ...
    def verify_public_boundary(self, *, repo_root: Path, rules_path: Path) -> Any: ...
    def audit_cost_coverage(
        self,
        data: dict[str, Any],
        *,
        pricing_path: Path,
        codex_state_path: Path,
        codex_logs_path: Path,
        codex_thread_id: str | None,
        cwd: Path,
        claude_root: Path = ...,
    ) -> CostAuditReport: ...
    def load_metrics(self, path: Path) -> dict[str, Any]: ...
    def recompute_summary(self, data: dict[str, Any]) -> None: ...
    def print_summary(self, data: dict[str, Any], history_signals: HistorySignals | None = ...) -> None: ...
    def render_summary_json(self, data: dict[str, Any], history_signals: HistorySignals | None = ...) -> str: ...
    def read_history_signals(self, warehouse_path: Path, project_cwd: Path, data: dict[str, Any]) -> HistorySignals | None: ...
    def audit_history(self, data: dict[str, Any]) -> AuditReport: ...
    def render_audit_report(self, report: AuditReport) -> str: ...
    def render_audit_report_json(self, report: AuditReport) -> str: ...
    def compare_metrics_to_history(
        self,
        data: dict[str, Any],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
    ) -> HistoryCompareReport: ...
    def render_history_compare_report(self, report: HistoryCompareReport) -> str: ...
    def render_history_compare_report_json(self, report: HistoryCompareReport) -> str: ...
    def metrics_mutation_lock(self, path: Path) -> Any: ...
    def render_ingest_summary_json(self, summary: IngestSummary) -> str: ...
    def render_normalize_summary_json(self, summary: NormalizeSummary) -> str: ...
    def render_classify_summary_json(self, summary: ClassifySummary) -> str: ...
    def render_derive_summary_json(self, summary: DeriveSummary) -> str: ...
    def derive_retro_timeline(
        self,
        data: dict[str, Any],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
        window_size: int,
    ) -> RetroTimelineReport: ...
    def render_retro_timeline_report(self, report: RetroTimelineReport) -> str: ...
    def render_retro_timeline_report_json(self, report: RetroTimelineReport) -> str: ...
    def render_cost_audit_report_json(self, report: CostAuditReport) -> str: ...
    def resolve_pricing_path(self, cwd: Path) -> Path: ...
    def merge_tasks(self, data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]: ...
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
        claude_root: Path = ...,
    ) -> dict[str, Any]: ...


_COMMAND_TO_EVENT_TYPE: dict[str, str] = {
    "start-task": "goal_started",
    "continue-task": "goal_continued",
    "finish-task": "goal_finished",
}


def _command_to_event_type(command: str | None) -> str:
    return _COMMAND_TO_EVENT_TYPE.get(command or "", "goal_updated")


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
        f"exec '{python_executable}' -m ai_agents_metrics \"$@\"\n"
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
        f"exec '{python_executable}' -m ai_agents_metrics \"$@\"\n"
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
        print("Then reopen your shell before running `ai-agents-metrics` by command name.")
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
    with metrics_mutation_lock(metrics_path):
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

    with metrics_mutation_lock(metrics_path):
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
    _warehouse_raw = getattr(args, "warehouse_path", "")
    # Guard against the empty-string case: Path("").expanduser() resolves to Path(".")
    # which always exists and causes an unintended SQLite connect attempt.
    warehouse_path = Path(_warehouse_raw).expanduser() if _warehouse_raw else Path("")
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
    with metrics_mutation_lock(metrics_path):
        data = load_metrics(metrics_path)
        resolution = cli_module.ensure_active_task(data, Path.cwd())
        if resolution.status == "created" and resolution.goal_id is not None:
            created_goal = get_task(data["goals"], resolution.goal_id)
            goal_entries = get_goal_entries(data["entries"], resolution.goal_id)
            append_event(metrics_path, "goal_started", goal=created_goal, entries=goal_entries)
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


def _run_ingest(
    source: str,
    source_root_arg: str | None,
    warehouse_path: Path,
    cli_module: CommandRuntime,
) -> tuple[dict[str, IngestSummary], list[str], str | None]:
    """Run ingest for the resolved source(s).

    Returns (summaries_by_source, skipped_source_names, error_message).
    error_message is non-None for invalid argument combinations.
    """
    if source == "all":
        if source_root_arg is not None:
            return {}, [], "--source-root cannot be used with --source all"
        summaries: dict[str, IngestSummary] = {}
        skipped: list[str] = []
        for src_name, src_root in [("codex", Path.home() / ".codex"), ("claude", Path.home() / ".claude")]:
            if not src_root.exists():
                skipped.append(src_name)
                continue
            with cli_module.metrics_mutation_lock(warehouse_path):
                summaries[src_name] = cli_module.ingest_codex_history(src_root, warehouse_path, src_name)
        return summaries, skipped, None

    if source_root_arg is not None:
        source_root = Path(source_root_arg).expanduser()
    elif source == "claude":
        source_root = Path.home() / ".claude"
    else:
        source_root = Path.home() / ".codex"
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.ingest_codex_history(source_root, warehouse_path, source)
    return {source: summary}, [], None


def handle_ingest_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    import json as _json
    import sys

    source_root_arg: str | None = getattr(args, "source_root", None)
    source: str = getattr(args, "source", None) or ("codex" if source_root_arg is not None else "all")
    json_output: bool = getattr(args, "json", False)
    warehouse_path = Path(args.warehouse_path).expanduser()

    summaries, skipped, error = _run_ingest(source, source_root_arg, warehouse_path, cli_module)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if source == "all":
        if json_output:
            print(_json.dumps({k: _json.loads(cli_module.render_ingest_summary_json(v)) for k, v in summaries.items()}))
        else:
            for src_name in skipped:
                print(f"Skipping {src_name}: {Path.home() / ('.' + src_name)} not found")
            for src_name, summary in summaries.items():
                print(f"[{src_name}] Ingested into {summary.warehouse_path}")
                print(f"  Source root: {summary.source_root}")
                print(f"  Scanned files: {summary.scanned_files}")
                print(f"  Imported files: {summary.imported_files}")
                print(f"  Skipped files: {summary.skipped_files}")
                print(f"  Projects: {summary.projects}")
                print(f"  Threads: {summary.threads}")
                print(f"  Sessions: {summary.sessions}")
                print(f"  Session events: {summary.session_events}")
                print(f"  Token usage events: {summary.token_usage_events}")
                print(f"  Total tokens: {summary.total_tokens}")
                print(f"  Messages: {summary.messages}")
        return 0

    summary = next(iter(summaries.values()))
    if json_output:
        print(cli_module.render_ingest_summary_json(summary))
    else:
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
    if getattr(args, "json", False):
        print(cli_module.render_normalize_summary_json(summary))
    else:
        print(f"Normalized Codex history in {summary.warehouse_path}")
        print(f"Projects: {summary.projects}")
        print(f"Threads: {summary.threads}")
        print(f"Sessions: {summary.sessions}")
        print(f"Messages: {summary.messages}")
        print(f"Usage events: {summary.usage_events}")
        print(f"Logs: {summary.logs}")
    return 0


def handle_classify_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.classify_codex_history(warehouse_path)
    if getattr(args, "json", False):
        print(cli_module.render_classify_summary_json(summary))
    else:
        print(f"Classified session kinds in {summary.warehouse_path}")
        print(f"Classifier version: {summary.classifier_version}")
        print(f"Sessions total: {summary.sessions_total}")
        print(f"Main sessions: {summary.main_sessions}")
        print(f"Subagent sessions: {summary.subagent_sessions}")
        print(f"Unknown sessions: {summary.unknown_sessions}")
        if summary.practice_event_classifier_version:
            print(f"Practice events: {summary.practice_events_total}")
            if summary.practice_events_by_family:
                families = ", ".join(f"{family}={count}" for family, count in summary.practice_events_by_family)
                print(f"Practice events by family: {families}")
    return 0


def handle_derive_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.derive_codex_history(warehouse_path)
    if getattr(args, "json", False):
        print(cli_module.render_derive_summary_json(summary))
    else:
        print(f"Derived Codex history in {summary.warehouse_path}")
        print(f"Projects: {summary.projects}")
        print(f"Goals: {summary.goals}")
        print(f"Attempts: {summary.attempts}")
        print(f"Timeline events: {summary.timeline_events}")
        print(f"Retry chains: {summary.retry_chains}")
        print(f"Message facts: {summary.message_facts}")
        print(f"Session usage: {summary.session_usage}")
        print(f"Token coverage: {summary.token_covered_sessions}/{summary.session_usage} sessions")
    return 0


def _print_empty_history_guidance(source: str) -> None:
    """Print actionable next steps when no agent history is found on first run.

    Called from ``handle_history_update`` when the default-location scan
    finds no Codex or Claude Code history files. The tool's core value
    proposition is extracting signals from these history files — a fresh
    user seeing a terse "nothing to normalize" line does not know whether
    the tool is broken, whether their history is in the wrong place, or
    whether they need to generate some agent activity first.
    """
    claude_dir = Path.home() / ".claude"
    codex_dir = Path.home() / ".codex"
    print()
    print("No agent history was found at the default locations:")
    if source in ("all", "claude"):
        print(f"  - Claude Code: {claude_dir} (not found)")
    if source in ("all", "codex"):
        print(f"  - Codex:       {codex_dir} (not found)")
    print()
    print("What to try next:")
    print("  1. If you have not yet used Claude Code or Codex on this machine,")
    print("     start an agent session first, then rerun `ai-agents-metrics history-update`.")
    print("  2. If your agent history is in a non-default location, point to it:")
    print("       ai-agents-metrics history-update --claude-root /path/to/.claude")
    print("       ai-agents-metrics history-update --codex-state-path /path/to/.codex")
    print("  3. To scan only one source at a time:")
    print("       ai-agents-metrics history-update --source claude")
    print("       ai-agents-metrics history-update --source codex")


def handle_history_update(args: Namespace, cli_module: CommandRuntime) -> int:
    """Run the full history pipeline: ingest → normalize → derive."""
    import json as _json
    import sys

    source_root_arg: str | None = getattr(args, "source_root", None)
    source: str = getattr(args, "source", None) or ("codex" if source_root_arg is not None else "all")
    warehouse_path = Path(args.warehouse_path).expanduser()
    json_output: bool = getattr(args, "json", False)

    ingest_results, ingest_skipped, error = _run_ingest(source, source_root_arg, warehouse_path, cli_module)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    ingest_summaries: dict[str, object] = {}
    if source == "all":
        for src_name in ingest_skipped:
            if not json_output:
                print(f"==> history-ingest ({src_name}) [skipped: {Path.home() / ('.' + src_name)} not found]")
        for src_name, ingest_summary in ingest_results.items():
            if not json_output:
                print(f"==> history-ingest ({src_name})")
                print(f"    Imported {ingest_summary.imported_files} files, {ingest_summary.threads} threads")
            else:
                ingest_summaries[src_name] = _json.loads(cli_module.render_ingest_summary_json(ingest_summary))
    else:
        ingest_summary = next(iter(ingest_results.values()))
        if not json_output:
            print("==> history-ingest")
            print(f"    Imported {ingest_summary.imported_files} files, {ingest_summary.threads} threads")
        else:
            ingest_summaries = {source: _json.loads(cli_module.render_ingest_summary_json(ingest_summary))}

    if not ingest_results and not warehouse_path.exists():
        if not json_output:
            _print_empty_history_guidance(source)
        else:
            print(_json.dumps({"ingest": ingest_summaries, "normalize": None, "derive": None}))
        return 0


    if not json_output:
        print("==> history-normalize")
    with cli_module.metrics_mutation_lock(warehouse_path):
        normalize_summary = cli_module.normalize_codex_history(warehouse_path)
    if not json_output:
        print(f"    {normalize_summary.threads} threads, {normalize_summary.messages} messages")
        print("==> history-classify")
    with cli_module.metrics_mutation_lock(warehouse_path):
        classify_summary = cli_module.classify_codex_history(warehouse_path)
    if not json_output:
        print(
            f"    {classify_summary.main_sessions} main, {classify_summary.subagent_sessions} subagent, "
            f"{classify_summary.unknown_sessions} unknown"
        )
        if classify_summary.practice_event_classifier_version:
            print(f"    {classify_summary.practice_events_total} practice events")
        print("==> history-derive")
    with cli_module.metrics_mutation_lock(warehouse_path):
        derive_summary = cli_module.derive_codex_history(warehouse_path)
    if not json_output:
        print(f"    {derive_summary.goals} goals, {derive_summary.retry_chains} retry chains")
        print(f"Done. Warehouse: {warehouse_path}")
    else:
        print(
            _json.dumps(
                {
                    "ingest": ingest_summaries,
                    "normalize": _json.loads(cli_module.render_normalize_summary_json(normalize_summary)),
                    "classify": _json.loads(cli_module.render_classify_summary_json(classify_summary)),
                    "derive": _json.loads(cli_module.render_derive_summary_json(derive_summary)),
                }
            )
        )
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
    if getattr(args, "json", False):
        print(cli_module.render_retro_timeline_report_json(report))
    else:
        print(cli_module.render_retro_timeline_report(report))
    return 0


def handle_audit_cost_coverage(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    pricing_path = Path(args.pricing_path) if args.pricing_path else cli_module.resolve_pricing_path(Path.cwd())
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    claude_root = Path(args.claude_root) if getattr(args, "claude_root", None) is not None else Path.home() / ".claude"
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.audit_cost_coverage(
        data,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        codex_thread_id=args.codex_thread_id,
        cwd=Path.cwd(),
        claude_root=claude_root,
    )
    if getattr(args, "json", False):
        print(cli_module.render_cost_audit_report_json(report))
    else:
        print(render_cost_audit_report(report))
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
    pricing_path = Path(args.pricing_path) if args.pricing_path else cli_module.resolve_pricing_path(Path.cwd())
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
            goals=relinked_goals if relinked_goals else None,
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
    pricing_path = Path(args.pricing_path) if args.pricing_path else cli_module.resolve_pricing_path(Path.cwd())
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


def handle_render_report(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    report_path = Path(args.report_path)
    data = load_metrics(metrics_path)
    cli_module.save_report(report_path, data)
    print(f"Rendered markdown report: {report_path}")
    return 0


def handle_render_html(args: Namespace, _cli_module: CommandRuntime) -> int:
    import sqlite3
    from datetime import datetime, timezone

    from ai_agents_metrics.html_report import (
        aggregate_report_data,
        check_warehouse_state,
        render_html_report,
    )

    metrics_path = Path(args.metrics_path)
    output_path = Path(args.output)
    days: int | None = args.days

    data = load_metrics(metrics_path)
    goals: list[dict] = data.get("goals", [])

    # Load retry and token data from warehouse when available.
    warehouse_retry: dict[str, dict[str, int]] | None = None
    warehouse_tokens: list[tuple[str, str | None, int, int, int]] | None = None
    warehouse_practice: list[tuple[str, str, int]] | None = None
    cwd = str(Path.cwd())
    _warehouse_arg = getattr(args, "warehouse_path", "") or ""
    warehouse_path = Path(_warehouse_arg) if _warehouse_arg else None
    if warehouse_path is None or not warehouse_path.is_file():
        # Fall back to the default warehouse location beside the metrics file.
        warehouse_path = default_raw_warehouse_path(metrics_path)
    warehouse_state = check_warehouse_state(warehouse_path, cwd)
    # Only query warehouse when it will actually yield usable rows. An empty
    # empty_for_cwd path would otherwise produce "warehouse-source" charts
    # with all-zero values, conflicting with the ledger-fallback badge and
    # callout shown to the user.
    if warehouse_state.get("status") == "ok" and warehouse_path.is_file():
        try:
            with sqlite3.connect(warehouse_path) as conn:
                # Use main_attempt_count (H-040 classifier) to distinguish real
                # main-agent retries from subagent Task() spawns, which also
                # produce separate session JSONL files and would otherwise
                # inflate retry_count. COALESCE treats unclassified rows as
                # single-attempt (conservative — no false retry signal).
                retry_rows = conn.execute(
                    "SELECT last_seen_at, "
                    "  COALESCE(main_attempt_count, 1) as main_attempts "
                    "FROM derived_goals "
                    "WHERE cwd = ? AND last_seen_at IS NOT NULL",
                    (cwd,),
                ).fetchall()
                token_rows = conn.execute(
                    "SELECT dg.last_seen_at, "
                    "  COALESCE(dg.model, ("
                    "    SELECT json_extract(nue.raw_json, '$.message.model') "
                    "    FROM normalized_usage_events nue "
                    "    WHERE nue.thread_id = dg.thread_id "
                    "      AND json_extract(nue.raw_json, '$.message.model') IS NOT NULL "
                    "    LIMIT 1"
                    "  )) as model, "
                    "  COALESCE(SUM(dsu.input_tokens), 0), "
                    "  COALESCE(SUM(dsu.cached_input_tokens), 0), "
                    "  COALESCE(SUM(dsu.output_tokens), 0) "
                    "FROM derived_goals dg "
                    "LEFT JOIN derived_session_usage dsu ON dsu.thread_id = dg.thread_id "
                    "WHERE dg.cwd = ? AND dg.last_seen_at IS NOT NULL "
                    "GROUP BY dg.thread_id",
                    (cwd,),
                ).fetchall()
                # Practice-event distribution, scoped to the current cwd via
                # the goals table so foreign repos' events don't bleed in.
                practice_rows = conn.execute(
                    "SELECT pe.practice_name, pe.source_kind, COUNT(*) "
                    "FROM derived_practice_events pe "
                    "JOIN derived_goals dg ON dg.thread_id = pe.thread_id "
                    "WHERE dg.cwd = ? "
                    "GROUP BY pe.practice_name, pe.source_kind",
                    (cwd,),
                ).fetchall()
            by_day: dict[str, dict[str, int]] = {}
            for last_seen_at, main_attempts in retry_rows:
                day = last_seen_at[:10]
                if day not in by_day:
                    by_day[day] = {"threads": 0, "retry_threads": 0}
                by_day[day]["threads"] += 1
                if main_attempts and main_attempts > 1:
                    by_day[day]["retry_threads"] += 1
            warehouse_retry = by_day
            warehouse_tokens = [
                (last_seen_at, model, inp, cac, out)
                for last_seen_at, model, inp, cac, out in token_rows
            ]
            warehouse_practice = [
                (name, source_kind, count)
                for name, source_kind, count in practice_rows
            ]
        except (sqlite3.Error, OSError):
            pass  # warehouse unavailable or schema mismatch — fall back to ledger

    # Load model pricing for token-cost breakdown in chart 3.
    pricing: dict[str, dict[str, float | None]] | None = None
    try:
        from ai_agents_metrics.usage_resolution import PRICING_JSON_PATH, load_pricing
        pricing = load_pricing(PRICING_JSON_PATH)
    except Exception:
        pricing = None

    chart_data = aggregate_report_data(
        goals, days,
        warehouse_retry=warehouse_retry,
        warehouse_tokens=warehouse_tokens,
        pricing=pricing,
        warehouse_practice=warehouse_practice,
        warehouse_state=warehouse_state,
    )
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = render_html_report(chart_data, generated_at)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    retry_src = "warehouse" if warehouse_retry is not None else "ledger"
    token_src = "warehouse" if warehouse_tokens is not None else "ledger"
    practice_n = sum(c for _, _, c in warehouse_practice) if warehouse_practice else 0
    practice_src = f"warehouse ({practice_n} events)" if warehouse_practice else "none"
    wh_status = warehouse_state.get("status", "ok")
    print(
        f"Rendered HTML report: {output_path} "
        f"(retry: {retry_src}, tokens: {token_src}, practice: {practice_src}, "
        f"warehouse: {wh_status})"
    )
    return 0
