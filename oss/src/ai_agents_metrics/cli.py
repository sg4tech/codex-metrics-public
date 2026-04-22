#!/usr/bin/env python3
"""Argparse CLI router; command handlers live in :mod:`commands`.

Parser construction lives in :mod:`cli_parsers` and path constants in
:mod:`cli_constants`. This file keeps the dispatch loop plus the facade
surface that ``scripts/metrics_cli.py`` re-exports for CLI tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_agents_metrics import commands, runtime_facade
from ai_agents_metrics.bootstrap import (
    BootstrapCallbacks,
    BootstrapPaths,
)
from ai_agents_metrics.bootstrap import (
    bootstrap_project as run_bootstrap_project,
)

# Re-exported at module scope so tests that monkeypatch ``cli.CLAUDE_ROOT``
# (test_metrics_cli.py uses ``monkeypatch.setattr(cli_module, "CLAUDE_ROOT", ...)``)
# keep working. Other path constants live in cli_constants and are only
# imported here when cli.py itself references them.
from ai_agents_metrics.cli_constants import (
    CLAUDE_ROOT,
    METRICS_JSON_PATH,
)
from ai_agents_metrics.cli_parsers import build_parser
from ai_agents_metrics.completion import render_completion
from ai_agents_metrics.cost_audit import (
    CostAuditContext,
    CostAuditReport,
)
from ai_agents_metrics.cost_audit import (
    audit_cost_coverage as _run_audit_cost_coverage,
)
from ai_agents_metrics.domain import (
    GoalRecord,
    default_metrics,
    load_metrics,
    recompute_summary,
)
from ai_agents_metrics.git_state import (
    ActiveTaskResolution,
    detect_started_work,
)
from ai_agents_metrics.git_state import (
    _is_meaningful_worktree_path as _git_state_is_meaningful_worktree_path,
)
from ai_agents_metrics.git_state import (
    _normalize_worktree_path as _git_state_normalize_worktree_path,
)
from ai_agents_metrics.history.classify import ClassifySummary
from ai_agents_metrics.history.classify import (
    classify_codex_history as run_classify_codex_history,
)
from ai_agents_metrics.history.derive import DeriveSummary
from ai_agents_metrics.history.derive import (
    derive_codex_history as run_derive_codex_history,
)
from ai_agents_metrics.history.ingest import IngestSummary
from ai_agents_metrics.history.ingest import (
    ingest_codex_history as run_ingest_codex_history,
)
from ai_agents_metrics.history.normalize import NormalizeSummary
from ai_agents_metrics.history.normalize import (
    normalize_codex_history as run_normalize_codex_history,
)
from ai_agents_metrics.observability import record_cli_invocation_observation
from ai_agents_metrics.public_boundary import PublicBoundaryReport
from ai_agents_metrics.public_boundary import (
    verify_public_boundary as run_verify_public_boundary,
)
from ai_agents_metrics.reporting import generate_report_md
from ai_agents_metrics.security import (
    SecurityReport,
    render_security_report,
)
from ai_agents_metrics.security import (
    verify_security as run_verify_security,
)
from ai_agents_metrics.storage import atomic_write_text, ensure_parent_dir
from ai_agents_metrics.usage_backends import (
    ClaudeUsageBackend,
    UsageBackend,
    select_usage_backend,
)
from ai_agents_metrics.usage_backends import (
    resolve_usage_window as resolve_backend_usage_window,
)
from ai_agents_metrics.usage_resolution import find_usage_thread_id
from ai_agents_metrics.workflow_fsm import (
    WorkflowEvent,
    WorkflowResolution,
    resolve_workflow_transition,
)

if TYPE_CHECKING:
    import argparse


def _normalize_worktree_path(path_text: str) -> str:
    return _git_state_normalize_worktree_path(path_text)


def _is_meaningful_worktree_path(path_text: str) -> bool:
    return _git_state_is_meaningful_worktree_path(path_text)


def ingest_codex_history(source_root: Path, warehouse_path: Path, source: str = "codex") -> IngestSummary:
    return run_ingest_codex_history(source_root=source_root, warehouse_path=warehouse_path, source=source)


def normalize_codex_history(warehouse_path: Path) -> NormalizeSummary:
    return run_normalize_codex_history(warehouse_path=warehouse_path)


def derive_codex_history(warehouse_path: Path) -> DeriveSummary:
    return run_derive_codex_history(warehouse_path=warehouse_path)


def classify_codex_history(warehouse_path: Path) -> ClassifySummary:
    return run_classify_codex_history(warehouse_path=warehouse_path)


def verify_public_boundary(*, repo_root: Path, rules_path: Path) -> PublicBoundaryReport:
    return run_verify_public_boundary(repo_root=repo_root, rules_path=rules_path)


def security(*, repo_root: Path, rules_path: Path) -> SecurityReport:
    return run_verify_security(repo_root=repo_root, rules_path=rules_path)


def get_active_goals(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [goal for goal in data["goals"] if goal.get("status") == "in_progress"]


def resolve_workflow_resolution(data: dict[str, Any], cwd: Path, event: WorkflowEvent) -> WorkflowResolution:
    report = detect_started_work(cwd)
    return resolve_workflow_transition(
        active_goal_count=len(get_active_goals(data)),
        started_work_detected=report.started_work_detected if report.git_available else None,
        git_available=report.git_available,
        event=event,
    )


def build_active_task_warning(data: dict[str, Any], cwd: Path) -> str | None:
    resolution = resolve_workflow_resolution(data, cwd, WorkflowEvent.SHOW)
    if resolution.decision.action != "warning":
        return None
    return f"Warning: {resolution.decision.message}."


def ensure_active_task(data: dict[str, Any], cwd: Path) -> ActiveTaskResolution:
    # Delegates to runtime_facade (same body, kept as a re-exported surface
    # for scripts/metrics_cli.py and tests).
    return runtime_facade.ensure_active_task(data, cwd)


def resolve_usage_costs(
    *,
    pricing_path: Path,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    explicit_cost_fields_used: bool,
    explicit_token_fields_used: bool,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    # Delegates to runtime_facade (same body).
    return runtime_facade.resolve_usage_costs(
        pricing_path=pricing_path,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        explicit_cost_fields_used=explicit_cost_fields_used,
        explicit_token_fields_used=explicit_token_fields_used,
    )


def save_report(path: Path, data: dict[str, Any]) -> None:
    report = generate_report_md(data)
    atomic_write_text(path, report)


def init_files(metrics_path: Path, report_path: Path | None, force: bool = False) -> None:
    if not force:
        existing_paths = [path for path in (metrics_path, report_path) if path is not None and path.exists()]
        if existing_paths:
            joined_paths = ", ".join(str(path) for path in existing_paths)
            raise ValueError(
                f"Metrics files already exist: {joined_paths}. Use --force to overwrite."
            )
    ensure_parent_dir(metrics_path)
    metrics_path.write_text("", encoding="utf-8")
    if report_path is not None:
        data = default_metrics()
        recompute_summary(data)
        save_report(report_path, data)


def bootstrap_project(
    *,
    target_dir: Path,
    metrics_path: Path,
    report_path: Path | None,
    policy_path: Path,
    command_path: Path,
    agents_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    del target_dir
    result = run_bootstrap_project(
        paths=BootstrapPaths(
            metrics_path=metrics_path,
            report_path=report_path,
            policy_path=policy_path,
            command_path=command_path,
            agents_path=agents_path,
        ),
        force=force,
        dry_run=dry_run,
        callbacks=BootstrapCallbacks(
            load_metrics=load_metrics,
            default_metrics=default_metrics,
            save_report=save_report,
        ),
    )
    return result.messages



# Delegates to runtime_facade.resolve_goal_usage_updates; cli.resolve_goal_usage_updates
# is preserved as a re-exported surface for scripts/metrics_cli.py and tests that
# import it via `cli_module.resolve_goal_usage_updates`. The return NamedTuple from
# runtime_facade is a tuple subclass so positional destructuring still works.
def resolve_goal_usage_updates(  # pylint: disable=too-many-arguments
    *,
    task: GoalRecord,
    usage_backend: UsageBackend | None = None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    claude_root: Path = CLAUDE_ROOT,
) -> tuple[
    float | None,
    int | None,
    int | None,
    int | None,
    int | None,
    str | None,
    float | None,
    int | None,
    int | None,
    int | None,
    int | None,
    str | None,
    str | None,
]:
    return runtime_facade.resolve_goal_usage_updates(
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


# Mirrors runtime_facade.upsert_task; the wide kwargs surface reflects the
# `update`/`start-task`/`finish-task` argparse contract.
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
    return runtime_facade.upsert_task(
        data=data,
        task_id=task_id,
        title=title,
        task_type=task_type,
        continuation_of=continuation_of,
        supersedes_task_id=supersedes_task_id,
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
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        codex_thread_id=codex_thread_id,
        cwd=cwd,
        claude_root=claude_root,
        usage_backend=usage_backend,
    )


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
    return runtime_facade.sync_usage(
        data=data,
        cwd=cwd,
        pricing_path=pricing_path,
        usage_state_path=usage_state_path,
        usage_logs_path=usage_logs_path,
        usage_thread_id=usage_thread_id,
        usage_backend=usage_backend,
        claude_root=claude_root,
    )


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


def audit_cost_coverage(
    data: dict[str, Any],
    *,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    claude_root: Path = CLAUDE_ROOT,
) -> CostAuditReport:
    def resolve_cost_audit_usage_window(
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> tuple[float | None, int | None]:
        if agent_name == "claude":
            backend: UsageBackend = ClaudeUsageBackend()
        else:
            backend = select_usage_backend(state_path, cwd, thread_id)
        window = resolve_backend_usage_window(
            backend,
            state_path=state_path,
            logs_path=logs_path,
            cwd=cwd,
            started_at=started_at,
            finished_at=finished_at,
            pricing_path=pricing_path,
            thread_id=thread_id,
        )
        return window.cost_usd, window.total_tokens

    return _run_audit_cost_coverage(
        data,
        context=CostAuditContext(
            pricing_path=pricing_path,
            codex_state_path=codex_state_path,
            codex_logs_path=codex_logs_path,
            claude_root=claude_root,
            cwd=cwd,
            codex_thread_id=codex_thread_id,
            find_thread_id=find_usage_thread_id,
            resolve_usage_window=resolve_cost_audit_usage_window,
        ),
    )


def merge_tasks(data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]:
    # Delegate to the decomposed facade implementation (same behaviour) to avoid
    # duplicating the branch-heavy body; cli.merge_tasks is preserved as a
    # re-exported surface for scripts/metrics_cli.py and test_metrics_domain.py.
    return runtime_facade.merge_tasks(data, keep_task_id, drop_task_id)


def _record_cli_invocation(args: argparse.Namespace) -> None:
    metrics_path = Path(getattr(args, "metrics_path", METRICS_JSON_PATH))
    command = getattr(args, "command", None)
    if command is None:
        return
    payload: dict[str, Any] = {}
    task_id = getattr(args, "task_id", None)
    if task_id is not None:
        payload["task_id"] = task_id
    keep_task_id = getattr(args, "keep_task_id", None)
    if keep_task_id is not None:
        payload["keep_task_id"] = keep_task_id
    drop_task_id = getattr(args, "drop_task_id", None)
    if drop_task_id is not None:
        payload["drop_task_id"] = drop_task_id
    record_cli_invocation_observation(
        metrics_path,
        command=command,
        cwd=str(Path.cwd()),
        task_id=task_id,
        extra_payload=payload,
    )


def _handle_completion(args: argparse.Namespace) -> int:
    print(render_completion(build_parser(), args.shell), end="")
    return 0


def _handle_security(args: argparse.Namespace) -> int:
    report = security(
        repo_root=Path(args.repo_root).expanduser(),
        rules_path=Path(args.rules_path).expanduser(),
    )
    print(render_security_report(report))
    return 0 if not report.findings else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    _record_cli_invocation(args)

    # Commands that delegate to commands.handle_*(args, runtime_facade).
    dispatch: dict[str, Any] = {
        "init": commands.handle_init,
        "show": commands.handle_show,
        "bootstrap": commands.handle_bootstrap,
        "install-self": commands.handle_install_self,
        "start-task": commands.handle_start_task,
        "continue-task": commands.handle_continue_task,
        "finish-task": commands.handle_finish_task,
        "history-audit": commands.handle_audit_history,
        "history-compare": commands.handle_compare_metrics_to_history,
        "history-ingest": commands.handle_ingest_codex_history,
        "history-normalize": commands.handle_normalize_codex_history,
        "history-classify": commands.handle_classify_codex_history,
        "history-derive": commands.handle_derive_codex_history,
        "history-update": commands.handle_history_update,
        "derive-retro-timeline": commands.handle_derive_retro_timeline,
        "audit-cost-coverage": commands.handle_audit_cost_coverage,
        "verify-public-boundary": commands.handle_verify_public_boundary,
        "ensure-active-task": commands.handle_ensure_active_task,
        "sync-usage": commands.handle_sync_usage,
        "sync-codex-usage": commands.handle_sync_codex_usage,
        "merge-tasks": commands.handle_merge_tasks,
        "render-report": commands.handle_render_report,
        "render-html": commands.handle_render_html,
        "update": commands.handle_update,
    }
    handler = dispatch.get(args.command)
    if handler is not None:
        return int(handler(args, runtime_facade))

    # Commands with unique argument shapes stay in dedicated helpers.
    if args.command == "completion":
        return _handle_completion(args)
    if args.command == "security":
        return _handle_security(args)

    parser.error("Unknown command")
    return 2


def console_main() -> int:
    try:
        return main()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(console_main())
