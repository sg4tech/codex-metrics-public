#!/usr/bin/env python3
# pylint: disable=too-many-lines  # cli.py is a router/dispatcher/shim that will shrink as commands are extracted; tracked as a separate splitting task
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

# runtime_facade and commands used only to be lazy-imported inside main/
# merge_tasks/delegate wrappers to avoid pulling the orchestration graph
# into the cli re-export shim (scripts/metrics_cli.py). In practice every
# cli entry already imports most of the orchestration transitively, and
# runtime_facade does not import cli (enforced by import-linter), so the
# lazy pattern costs more in ceremony than it saves in startup time.
from ai_agents_metrics import __version__, commands, runtime_facade
from ai_agents_metrics.bootstrap import (
    BootstrapCallbacks,
    BootstrapPaths,
)
from ai_agents_metrics.bootstrap import (
    bootstrap_project as run_bootstrap_project,
)
from ai_agents_metrics.completion import render_completion
from ai_agents_metrics.cost_audit import (
    CostAuditContext,
    CostAuditReport,
)
from ai_agents_metrics.cost_audit import (
    audit_cost_coverage as _run_audit_cost_coverage,
)
from ai_agents_metrics.domain import (
    ALLOWED_FAILURE_REASONS,
    ALLOWED_RESULT_FITS,
    ALLOWED_STATUSES,
    ALLOWED_TASK_TYPES,
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
from ai_agents_metrics.history.ingest import (
    IngestSummary,
    default_raw_warehouse_path,
)
from ai_agents_metrics.history.ingest import (
    ingest_codex_history as run_ingest_codex_history,
)
from ai_agents_metrics.history.normalize import NormalizeSummary
from ai_agents_metrics.history.normalize import (
    normalize_codex_history as run_normalize_codex_history,
)
from ai_agents_metrics.observability import record_cli_invocation_observation

# These two are not used in this module directly; they are re-exported so that
# scripts/metrics_cli.py (which does globals().update(vars(cli))) exposes them
# as MODULE.xxx in test_metrics_domain.py.  Remove once tests import directly.
from ai_agents_metrics.pricing_runtime import (  # pylint: disable=unused-import
    load_effective_pricing,  # noqa: F401
    resolve_effective_pricing_path,  # noqa: F401
)
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

# parse_usage_event, resolve_codex_usage_window, resolve_pricing_path,
# load_pricing, resolve_pricing_model_alias are not used here directly;
# re-exported for scripts/metrics_cli.py → MODULE surface accessed by tests.
# Remove once tests import directly.
from ai_agents_metrics.usage_resolution import (  # pylint: disable=unused-import
    find_usage_thread_id,
    load_pricing,  # noqa: F401
    parse_usage_event,  # noqa: F401
    resolve_codex_usage_window,  # noqa: F401
    resolve_pricing_model_alias,  # noqa: F401
    resolve_pricing_path,  # noqa: F401
)
from ai_agents_metrics.workflow_fsm import (
    WorkflowEvent,
    WorkflowResolution,
    resolve_workflow_transition,
)

EVENTS_NDJSON_PATH = Path("metrics/events.ndjson")
METRICS_JSON_PATH = EVENTS_NDJSON_PATH  # backward-compat alias used by args.metrics_path
REPORT_MD_PATH = Path("docs/ai-agents-metrics.md")
REPORT_HTML_PATH = Path("reports/report.html")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
CLAUDE_ROOT = Path.home() / ".claude"
RAW_WAREHOUSE_PATH = default_raw_warehouse_path(METRICS_JSON_PATH)
PUBLIC_BOUNDARY_RULES_PATH = Path("config/public-boundary-rules.toml")
SECURITY_RULES_PATH = Path("config/security-rules.toml")


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


def _detect_module_prog() -> str | None:
    """Return a human-readable prog name when invoked as ``python -m ai_agents_metrics``."""
    argv0 = sys.argv[0] if sys.argv else ""
    if os.path.basename(argv0) == "__main__.py":
        py = f"python{sys.version_info.major}.{sys.version_info.minor}"
        return f"{py} -m ai_agents_metrics"
    return None


#: Commands that are registered and fully functional but are hidden from the
#: top-level ``--help`` subparser listing to keep the first-time user experience
#: scannable. They are still discoverable via ``<cmd> --help`` and are listed
#: by name in the parser epilog so users know they exist.
_HIDDEN_FROM_TOPLEVEL_HELP: frozenset[str] = frozenset({
    # Pipeline stages — users run the composite `history-update` instead.
    "history-ingest", "history-normalize", "history-classify", "history-derive",
    # Audit / debug — niche, not primary flow.
    "history-audit", "history-compare", "audit-cost-coverage", "derive-retro-timeline",
    # Manual-tracking adjuncts — the trio start/continue/finish covers the primary path.
    "update", "ensure-active-task", "sync-usage", "sync-codex-usage",
    # Maintenance / low-level.
    "init", "merge-tasks", "render-report", "verify-public-boundary", "security",
})


# argparse setup is inherently verbose — 26 subparsers each owning their own
# flags. Splitting into per-command helpers would trade one long function for
# 26 tiny ones with no reuse; a future task could cluster them once the CLI
# surface stabilises (see ARCH-021 follow-up note on splitting cli.py).
def build_parser() -> argparse.ArgumentParser:  # pylint: disable=too-many-locals,too-many-statements
    parser = argparse.ArgumentParser(
        prog=_detect_module_prog(),
        description="Analyze your AI agent work history, track spending, and optimize your workflow. Point it at your history files and see retry pressure, token cost, and session timeline — no manual setup required.",
        epilog=(
            "Additional commands (run `<command> --help` for details):\n"
            "  Manual tracking:   update, ensure-active-task, sync-usage, sync-codex-usage\n"
            "  History pipeline:  history-ingest, history-normalize, history-classify,\n"
            "                     history-derive\n"
            "  Audit / debug:     history-audit, history-compare, audit-cost-coverage,\n"
            "                     derive-retro-timeline\n"
            "  Maintenance:       init, merge-tasks, render-report,\n"
            "                     verify-public-boundary, security\n"
            "\n"
            "Examples:\n"
            "  %(prog)s history-update\n"
            "  %(prog)s show\n"
            "  %(prog)s render-html --output /tmp/report.html\n"
            "  %(prog)s bootstrap --target-dir /path/to/repo --dry-run\n"
            "  %(prog)s start-task --title \"Add CSV import\" --task-type product\n"
            "  %(prog)s continue-task --task-id 2026-03-29-001 --notes \"Retry after validation failure\"\n"
            "  %(prog)s finish-task --task-id 2026-03-29-001 --status success --notes \"Validated\"\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        # A short placeholder keeps the `usage:` header readable — argparse
        # would otherwise dump all 26 choice names in a single unwrapped blob.
        metavar="<command>",
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Create the metrics JSON source of truth",
        description=(
            "Create the low-level metrics source of truth file. "
            "Use --write-report when you also want a markdown export."
        ),
    )
    init_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    init_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    init_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing metrics files")

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Scaffold ai-agents-metrics into a repository, including an instructions file and policy",
        description=(
            "Create the full ai-agents-metrics repository scaffold: metrics artifact, "
            "docs/ai-agents-metrics-policy.md, and a managed ai-agents-metrics block inside your instructions file. "
            "Use --write-report when you also want the optional markdown export."
        ),
    )
    bootstrap_parser.add_argument("--target-dir", default=".", help="Repository root to initialize")
    bootstrap_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    bootstrap_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    bootstrap_parser.add_argument("--write-report", action="store_true", help="Also create or update the optional markdown report")
    bootstrap_parser.add_argument("--policy-path", default="docs/ai-agents-metrics-policy.md")
    bootstrap_parser.add_argument("--command-path", default="tools/ai-agents-metrics")
    bootstrap_parser.add_argument("--agents-path", "--instructions-path", dest="agents_path", default="AGENTS.md")
    bootstrap_parser.add_argument("--force", action="store_true", help="Replace conflicting scaffold files")
    bootstrap_parser.add_argument("--dry-run", action="store_true", help="Preview planned changes without writing files")

    install_self_parser = subparsers.add_parser(
        "install-self",
        help="Install this executable into ~/bin/ai-agents-metrics",
        description=(
            "Install the current ai-agents-metrics executable into a stable user-local location. "
            "On macOS/Linux this defaults to a symlink at ~/bin/ai-agents-metrics."
        ),
    )
    install_self_parser.add_argument("--target-dir", default=str(Path.home() / "bin"))
    install_self_parser.add_argument("--target-path")
    install_self_parser.add_argument("--command-name", default="ai-agents-metrics")
    install_self_parser.add_argument("--copy", action="store_true", help="Copy the executable instead of creating a symlink")
    install_self_parser.add_argument(
        "--write-shell-profile",
        action="store_true",
        help="Append the target directory to the detected shell profile when it is not already on PATH",
    )

    completion_parser = subparsers.add_parser(
        "completion",
        help="Print shell completion for bash or zsh",
        description=(
            "Print a shell completion script for ai-agents-metrics. "
            "Use this to enable command and option completion in bash or zsh."
        ),
    )
    completion_parser.add_argument("shell", choices=("bash", "zsh"))

    start_parser = subparsers.add_parser(
        "start-task",
        help="Create a new goal and record the first implementation pass",
        description=(
            "Create a new goal with attempts incremented for the first implementation pass. "
            "Use this when starting meaningful work on a new task."
        ),
    )
    start_parser.add_argument("--title", required=True, help="Goal title")
    start_parser.add_argument("--task-type", required=True, choices=sorted(ALLOWED_TASK_TYPES), help="Goal classification")
    start_linked_group = start_parser.add_mutually_exclusive_group()
    start_linked_group.add_argument("--continuation-of", help="Create a new goal linked to a previous closed goal")
    start_linked_group.add_argument("--supersedes-task-id", help="Create a replacement goal for a previous closed goal")
    start_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    start_parser.add_argument("--started-at", help="Explicit ISO8601 start timestamp")
    start_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    start_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    start_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    start_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    start_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    start_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    start_parser.add_argument("--pricing-path", default=None)
    start_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    start_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    start_parser.add_argument("--codex-thread-id")
    start_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    start_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    start_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    start_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    continue_parser = subparsers.add_parser(
        "continue-task",
        help="Record another implementation pass for an existing goal",
        description=(
            "Increment attempts for an existing goal and optionally attach notes, failure reason, "
            "or usage data for the new pass."
        ),
    )
    continue_parser.add_argument("--task-id", required=True, help="Existing goal identifier")
    continue_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    continue_parser.add_argument(
        "--failure-reason",
        choices=sorted(ALLOWED_FAILURE_REASONS),
        help="Primary failure reason for the new unsuccessful pass",
    )
    continue_parser.add_argument("--started-at", help="Explicit ISO8601 timestamp for the new pass")
    continue_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    continue_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    continue_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    continue_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    continue_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    continue_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    continue_parser.add_argument("--pricing-path", default=None)
    continue_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    continue_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    continue_parser.add_argument("--codex-thread-id")
    continue_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    continue_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    continue_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    continue_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    finish_parser = subparsers.add_parser(
        "finish-task",
        help="Close an existing goal as success or fail",
        description=(
            "Close an existing goal after implementation work is done. Use --status success for a validated "
            "completion or --status fail with a dominant failure reason when the goal did not succeed."
        ),
    )
    finish_parser.add_argument("--task-id", required=True, help="Existing goal identifier")
    finish_parser.add_argument("--status", required=True, choices=("success", "fail"), help="Final goal status")
    finish_parser.add_argument(
        "--failure-reason",
        choices=sorted(ALLOWED_FAILURE_REASONS),
        help="Primary failure reason. Required when closing a goal as fail.",
    )
    finish_parser.add_argument(
        "--result-fit",
        choices=sorted(ALLOWED_RESULT_FITS),
        help="Optional operator quality judgement for closed product goals",
    )
    finish_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    finish_parser.add_argument("--finished-at", help="Explicit ISO8601 finish timestamp")
    finish_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    finish_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    finish_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    finish_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    finish_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    finish_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    finish_parser.add_argument("--pricing-path", default=None)
    finish_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    finish_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    finish_parser.add_argument("--codex-thread-id")
    finish_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    finish_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    finish_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    finish_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    update_parser = subparsers.add_parser(
        "update",
        help="Create or update a goal record",
        description=(
            "Create a new goal or update an existing one. For new goals, omit --task-id and let the updater "
            "generate one. Use --attempts-delta for a new implementation pass, --supersedes-task-id for a "
            "replacement goal, and --task-type explicitly for new goals."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s --title \"Improve CLI help\" --task-type product --attempts-delta 1\n"
            "  %(prog)s --task-id 2026-03-29-010 --status success --notes \"Validated\"\n"
            "  %(prog)s --task-id 2026-03-29-011 --title \"Retry CLI help\" --task-type product --supersedes-task-id 2026-03-29-010 --status success\n"
            "  %(prog)s --title \"Write retro\" --task-type retro --attempts-delta 1 --status success\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    update_parser.add_argument(
        "--task-id",
        help=(
            "Stable goal identifier. Omit this for new goals and let the updater generate one. "
            "Pass it when updating an existing goal or replaying history."
        ),
    )
    update_parser.add_argument("--title", help="Goal title. Required for new goals.")
    update_parser.add_argument("--task-type", choices=sorted(ALLOWED_TASK_TYPES), help="Goal classification for new goals")
    linked_task_group = update_parser.add_mutually_exclusive_group()
    linked_task_group.add_argument("--continuation-of", help="Create a new goal linked to a previous closed goal")
    linked_task_group.add_argument("--supersedes-task-id", help="Create a replacement goal for a previous closed goal")
    update_parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES), help="Goal status")
    update_parser.add_argument("--attempts-delta", type=int, help="Increment attempts by this amount")
    update_parser.add_argument("--attempts", type=int, help="Set absolute attempts count")
    update_parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    update_parser.add_argument("--cost-usd", type=float, help="Set explicit USD cost")
    update_parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    update_parser.add_argument("--tokens", type=int, help="Set explicit token count")
    update_parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    update_parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    update_parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    update_parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    update_parser.add_argument("--pricing-path", default=None)
    update_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    update_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    update_parser.add_argument("--codex-thread-id")
    update_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))
    update_parser.add_argument("--failure-reason", choices=sorted(ALLOWED_FAILURE_REASONS), help="Primary failure reason for a failed goal")
    update_parser.add_argument(
        "--result-fit",
        choices=sorted(ALLOWED_RESULT_FITS),
        help="Operator quality judgement for closed product goals: exact_fit, partial_fit, or miss",
    )
    update_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    update_parser.add_argument("--started-at", help="Explicit ISO8601 start timestamp")
    update_parser.add_argument("--finished-at", help="Explicit ISO8601 finish timestamp")
    update_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    update_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    update_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    show_parser = subparsers.add_parser(
        "show",
        help="Print current summary and operator review",
        description="Print the current summary, cost coverage, and operator review.",
    )
    show_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    show_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="Path to the history warehouse SQLite file (default: auto-detected from metrics path)",
    )
    show_parser.add_argument("--json", action="store_true", help="Output summary as JSON")

    audit_parser = subparsers.add_parser(
        "history-audit",
        help="Flag suspicious history patterns for manual review",
        description=(
            "Analyze stored goal history and print audit candidates such as likely misses, "
            "partial-fit recoveries, stale in-progress goals, and low-cost-coverage product goals."
        ),
    )
    audit_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    compare_parser = subparsers.add_parser(
        "history-compare",
        help="Compare the structured metrics ledger against reconstructed agent history",
        description=(
            "Read the metrics source of truth and a derived agent history warehouse, then print an "
            "aggregate comparison for the current repository cwd."
        ),
    )
    compare_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    compare_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH))
    compare_parser.add_argument("--cwd", default=str(Path.cwd()))

    ingest_parser = subparsers.add_parser(
        "history-ingest",
        help="Ingest local agent history into a raw SQLite warehouse",
        description=(
            "Read thread metadata, session transcripts, telemetry events, and logs from a local "
            "agent history directory into a raw warehouse for later derivation. "
            "Supports Codex (~/.codex) and Claude Code (~/.claude)."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ingest_parser.add_argument(
        "--source",
        choices=["codex", "claude", "all"],
        default=None,
        help=(
            "Agent source to ingest (default: all):\n"
            "  codex   — reads ~/.codex only\n"
            "  claude  — reads ~/.claude only\n"
            "  all     — reads both ~/.codex and ~/.claude"
        ),
    )
    ingest_parser.add_argument(
        "--source-root",
        default=None,
        help="Override the agent history root directory (implies --source codex unless --source is set; incompatible with --source all)",
    )
    ingest_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path for raw imported data",
    )

    normalize_parser = subparsers.add_parser(
        "history-normalize",
        help="Normalize raw agent history into analysis-friendly tables",
        description=(
            "Read the raw warehouse populated by history-ingest and build normalized summary tables "
            "for downstream analysis."
        ),
    )
    normalize_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path that already contains raw imported data",
    )

    classify_parser = subparsers.add_parser(
        "history-classify",
        help="Classify agent session kinds (main vs subagent) from normalized history",
        description=(
            "Read the normalized warehouse populated by history-normalize and write "
            "derived_session_kinds — a deterministic, filename-based classification of "
            "each session file as 'main' or 'subagent'. Required before history-derive "
            "to avoid subagent-aliased retry counts (see oss/docs/findings/F-001)."
        ),
    )
    classify_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path that already contains normalized agent history",
    )
    classify_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output summary as JSON",
    )

    derive_parser = subparsers.add_parser(
        "history-derive",
        help="Derive analysis marts from normalized agent history",
        description=(
            "Read the normalized warehouse populated by history-normalize and build reusable "
            "analysis marts for goals, attempts, timelines, retry chains, and session usage."
        ),
    )
    derive_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path that already contains normalized agent history",
    )

    history_update_parser = subparsers.add_parser(
        "history-update",
        help="Run the full history pipeline: ingest → normalize → derive",
        description=(
            "Run all three history pipeline stages in sequence: history-ingest, history-normalize, "
            "history-derive. Use this for the initial setup or to refresh the warehouse after new "
            "agent sessions. Equivalent to running the three stages separately."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    history_update_parser.add_argument(
        "--source",
        choices=["codex", "claude", "all"],
        default=None,
        help=(
            "Agent source to ingest (default: all):\n"
            "  codex   — reads ~/.codex only\n"
            "  claude  — reads ~/.claude only\n"
            "  all     — reads both ~/.codex and ~/.claude"
        ),
    )
    history_update_parser.add_argument(
        "--source-root",
        default=None,
        help="Override the agent history root directory (implies --source codex unless --source is set; incompatible with --source all)",
    )
    history_update_parser.add_argument(
        "--warehouse-path",
        default=str(RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path",
    )
    history_update_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output all three stage summaries as a single JSON object",
    )

    retro_timeline_parser = subparsers.add_parser(
        "derive-retro-timeline",
        help="Derive before/after product-metric windows around retrospective events",
        description=(
            "Read normalized Codex history from main.normalized_messages, build a retrospective timeline dataset, "
            "write it into the SQLite warehouse, and print before/after product-metric windows around each retro."
        ),
    )
    retro_timeline_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    retro_timeline_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH))
    retro_timeline_parser.add_argument("--cwd", default=str(Path.cwd()))
    retro_timeline_parser.add_argument("--window-size", type=int, default=5)

    cost_audit_parser = subparsers.add_parser(
        "audit-cost-coverage",
        help="Explain why product goals are missing cost coverage",
        description=(
            "Inspect closed product goals and explain why cost coverage is missing, partial, or recoverable."
        ),
    )
    cost_audit_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    cost_audit_parser.add_argument("--pricing-path", default=None)
    cost_audit_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    cost_audit_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    cost_audit_parser.add_argument("--codex-thread-id")
    cost_audit_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    public_boundary_parser = subparsers.add_parser(
        "verify-public-boundary",
        help="Verify that a public repository tree does not contain private-only material",
        description=(
            "Check a candidate public repository tree against explicit public-boundary rules. "
            "Fail on forbidden paths, forbidden file types, unexpected roots, or private-content markers."
        ),
    )
    public_boundary_parser.add_argument("--repo-root", default=".")
    public_boundary_parser.add_argument("--rules-path", default=str(PUBLIC_BOUNDARY_RULES_PATH))

    security_parser = subparsers.add_parser(
        "security",
        help="Run a fast staged-file security scan",
        description=(
            "Scan staged changes for secrets, token patterns, private keys, and other dangerous data "
            "before it lands in git."
        ),
    )
    security_parser.add_argument("--repo-root", default=".")
    security_parser.add_argument("--rules-path", default=str(SECURITY_RULES_PATH))

    subparsers.add_parser(
        "ensure-active-task",
        help="Recover or verify active task bookkeeping from local git changes",
        description=(
            "Inspect the current git working tree for meaningful repository work and ensure that active task "
            "bookkeeping exists. If work has started without an active goal, create a recovery draft."
        ),
    ).add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    sync_parser = subparsers.add_parser(
        "sync-usage",
        help="Backfill usage and cost from local agent logs",
        description="Backfill known cost and token totals from local agent telemetry.",
    )
    sync_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    sync_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    sync_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    sync_parser.add_argument("--pricing-path", default=None)
    sync_parser.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(CODEX_STATE_PATH))
    sync_parser.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(CODEX_LOGS_PATH))
    sync_parser.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
    sync_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    sync_legacy_parser = subparsers.add_parser(
        "sync-codex-usage",
        help="Deprecated alias for sync-usage",
        description="Backfill known cost and token totals from local agent telemetry.",
    )
    sync_legacy_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    sync_legacy_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    sync_legacy_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    sync_legacy_parser.add_argument("--pricing-path", default=None)
    sync_legacy_parser.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(CODEX_STATE_PATH))
    sync_legacy_parser.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(CODEX_LOGS_PATH))
    sync_legacy_parser.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
    sync_legacy_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    merge_parser = subparsers.add_parser(
        "merge-tasks",
        help="Merge a dropped split goal into a kept goal",
        description="Recombine mistakenly split goal history into one kept goal.",
    )
    merge_parser.add_argument("--keep-task-id", required=True, help="Goal that should remain after the merge")
    merge_parser.add_argument("--drop-task-id", required=True, help="Goal that should be merged into the kept goal")
    merge_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    merge_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    merge_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    render_report_parser = subparsers.add_parser(
        "render-report",
        help="Render the optional markdown report from stored metrics",
        description="Generate docs/ai-agents-metrics.md on demand from the JSON source of truth.",
    )
    render_report_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    render_report_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))

    render_html_parser = subparsers.add_parser(
        "render-html",
        help="Render a self-contained HTML report with trend charts",
        description="Generate a static HTML file with four trend charts for human review.",
    )
    render_html_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    render_html_parser.add_argument(
        "--output",
        default=str(REPORT_HTML_PATH),
        help="Output path for the HTML file (default: reports/report.html)",
    )
    render_html_parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help="Limit the time window to the last N days",
    )
    # Default is empty so handle_render_html falls back to the
    # metrics-path-adjacent default warehouse (derived per call in commands.py).
    render_html_parser.add_argument(
        "--warehouse-path",
        default="",
        help="SQLite warehouse path (default: derived from --metrics-path)",
    )
    render_html_parser.add_argument(
        "--cwd",
        default="",
        metavar="PATH",
        help=(
            "Override the cwd used to filter warehouse rows (default: the "
            "current process cwd). Use this to query a cross-machine "
            "warehouse — e.g. --cwd /Users/viktor/PhpstormProjects/hhsave "
            "when rendering on Linux against a Mac-imported warehouse."
        ),
    )

    # Hide advanced / pipeline-internal commands from the top-level `--help`
    # listing without unregistering them. The commands remain callable and
    # `<cmd> --help` still renders their per-command help. The epilog lists
    # them by name so users know they exist. This mutates a private argparse
    # attribute (stable across Py 3.9–3.13) because argparse has no public API
    # to mark a subparser as hidden after creation.
    # pylint: disable=protected-access
    subparsers._choices_actions = [  # noqa: SLF001
        act for act in subparsers._choices_actions
        if act.dest not in _HIDDEN_FROM_TOPLEVEL_HELP
    ]
    # pylint: enable=protected-access

    return parser


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
