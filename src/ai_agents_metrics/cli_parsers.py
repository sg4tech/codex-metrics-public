"""Argparse parser construction for the CLI.

Exposes ``build_parser`` plus the shared flag-/subparser-factory helpers.
Separated from ``cli.py`` so the entrypoint file stays focused on dispatch
and the facade surface used by scripts/metrics_cli.py and tests.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ai_agents_metrics import __version__
from ai_agents_metrics.cli_constants import (
    CLAUDE_ROOT,
    CODEX_LOGS_PATH,
    CODEX_STATE_PATH,
    METRICS_JSON_PATH,
    PUBLIC_BOUNDARY_RULES_PATH,
    RAW_WAREHOUSE_PATH,
    REPORT_HTML_PATH,
    REPORT_MD_PATH,
    SECURITY_RULES_PATH,
)
from ai_agents_metrics.domain import (
    ALLOWED_FAILURE_REASONS,
    ALLOWED_RESULT_FITS,
    ALLOWED_STATUSES,
    ALLOWED_TASK_TYPES,
)


def _detect_module_prog() -> str | None:
    """Return a human-readable prog name when invoked as ``python -m ai_agents_metrics``."""
    argv0 = sys.argv[0] if sys.argv else ""
    if Path(argv0).name == "__main__.py":
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


def _add_goal_usage_flags(parser: argparse.ArgumentParser) -> None:
    """Shared model/token/pricing/path flags for start/continue/finish/update."""
    parser.add_argument("--cost-usd-add", type=float, help="Add explicit USD cost")
    parser.add_argument("--tokens-add", type=int, help="Add explicit token count")
    parser.add_argument("--model", help="Pricing model name for token-based cost calculation")
    parser.add_argument("--input-tokens", type=int, help="Input tokens for model-based pricing")
    parser.add_argument("--cached-input-tokens", type=int, help="Cached input tokens for model-based pricing")
    parser.add_argument("--output-tokens", type=int, help="Output tokens for model-based pricing")
    parser.add_argument("--pricing-path", default=None)
    parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    parser.add_argument("--codex-thread-id")
    parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))


def _add_report_output_flags(parser: argparse.ArgumentParser) -> None:
    """Shared metrics-path / report-path / --write-report trio."""
    parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    parser.add_argument("--report-path", default=str(REPORT_MD_PATH))
    parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")


def _add_init_and_bootstrap_parsers(subparsers: Any) -> None:
    init_parser = subparsers.add_parser(
        "init",
        help="Create the metrics JSON source of truth",
        description=(
            "Create the low-level metrics source of truth file. "
            "Use --write-report when you also want a markdown export."
        ),
    )
    _add_report_output_flags(init_parser)
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
    _add_report_output_flags(bootstrap_parser)
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


def _add_task_workflow_parsers(subparsers: Any) -> None:
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
    _add_goal_usage_flags(start_parser)
    _add_report_output_flags(start_parser)

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
    _add_goal_usage_flags(continue_parser)
    _add_report_output_flags(continue_parser)

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
    _add_goal_usage_flags(finish_parser)
    _add_report_output_flags(finish_parser)

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
            '  %(prog)s --title "Improve CLI help" --task-type product --attempts-delta 1\n'
            '  %(prog)s --task-id 2026-03-29-010 --status success --notes "Validated"\n'
            '  %(prog)s --task-id 2026-03-29-011 --title "Retry CLI help" --task-type product --supersedes-task-id 2026-03-29-010 --status success\n'
            '  %(prog)s --title "Write retro" --task-type retro --attempts-delta 1 --status success\n'
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
    update_parser.add_argument("--cost-usd", type=float, help="Set explicit USD cost")
    update_parser.add_argument("--tokens", type=int, help="Set explicit token count")
    _add_goal_usage_flags(update_parser)
    update_parser.add_argument("--failure-reason", choices=sorted(ALLOWED_FAILURE_REASONS), help="Primary failure reason for a failed goal")
    update_parser.add_argument(
        "--result-fit",
        choices=sorted(ALLOWED_RESULT_FITS),
        help="Operator quality judgement for closed product goals: exact_fit, partial_fit, or miss",
    )
    update_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    update_parser.add_argument("--started-at", help="Explicit ISO8601 start timestamp")
    update_parser.add_argument("--finished-at", help="Explicit ISO8601 finish timestamp")
    _add_report_output_flags(update_parser)

    subparsers.add_parser(
        "ensure-active-task",
        help="Recover or verify active task bookkeeping from local git changes",
        description=(
            "Inspect the current git working tree for meaningful repository work and ensure that active task "
            "bookkeeping exists. If work has started without an active goal, create a recovery draft."
        ),
    ).add_argument("--metrics-path", default=str(METRICS_JSON_PATH))


def _add_history_parsers(subparsers: Any) -> None:
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

    _source_choice_help = (
        "Agent source to ingest (default: all):\n"
        "  codex   — reads ~/.codex only\n"
        "  claude  — reads ~/.claude only\n"
        "  all     — reads both ~/.codex and ~/.claude"
    )
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
    ingest_parser.add_argument("--source", choices=["codex", "claude", "all"], default=None, help=_source_choice_help)
    ingest_parser.add_argument(
        "--source-root",
        default=None,
        help="Override the agent history root directory (implies --source codex unless --source is set; incompatible with --source all)",
    )
    ingest_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH), help="SQLite warehouse path for raw imported data")

    normalize_parser = subparsers.add_parser(
        "history-normalize",
        help="Normalize raw agent history into analysis-friendly tables",
        description=(
            "Read the raw warehouse populated by history-ingest and build normalized summary tables "
            "for downstream analysis."
        ),
    )
    normalize_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH), help="SQLite warehouse path that already contains raw imported data")

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
    classify_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH), help="SQLite warehouse path that already contains normalized agent history")
    classify_parser.add_argument("--json", action="store_true", default=False, help="Output summary as JSON")

    derive_parser = subparsers.add_parser(
        "history-derive",
        help="Derive analysis marts from normalized agent history",
        description=(
            "Read the normalized warehouse populated by history-normalize and build reusable "
            "analysis marts for goals, attempts, timelines, retry chains, and session usage."
        ),
    )
    derive_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH), help="SQLite warehouse path that already contains normalized agent history")

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
    history_update_parser.add_argument("--source", choices=["codex", "claude", "all"], default=None, help=_source_choice_help)
    history_update_parser.add_argument(
        "--source-root",
        default=None,
        help="Override the agent history root directory (implies --source codex unless --source is set; incompatible with --source all)",
    )
    history_update_parser.add_argument("--warehouse-path", default=str(RAW_WAREHOUSE_PATH), help="SQLite warehouse path")
    history_update_parser.add_argument("--json", action="store_true", default=False, help="Output all three stage summaries as a single JSON object")

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
        description="Inspect closed product goals and explain why cost coverage is missing, partial, or recoverable.",
    )
    cost_audit_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    cost_audit_parser.add_argument("--pricing-path", default=None)
    cost_audit_parser.add_argument("--codex-state-path", default=str(CODEX_STATE_PATH))
    cost_audit_parser.add_argument("--codex-logs-path", default=str(CODEX_LOGS_PATH))
    cost_audit_parser.add_argument("--codex-thread-id")
    cost_audit_parser.add_argument("--claude-root", default=str(CLAUDE_ROOT))


def _add_sync_and_render_parsers(subparsers: Any) -> None:
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

    for name in ("sync-usage", "sync-codex-usage"):
        sp = subparsers.add_parser(
            name,
            help="Backfill usage and cost from local agent logs" if name == "sync-usage" else "Deprecated alias for sync-usage",
            description="Backfill known cost and token totals from local agent telemetry.",
        )
        _add_report_output_flags(sp)
        sp.add_argument("--pricing-path", default=None)
        sp.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(CODEX_STATE_PATH))
        sp.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(CODEX_LOGS_PATH))
        sp.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
        sp.add_argument("--claude-root", default=str(CLAUDE_ROOT))

    merge_parser = subparsers.add_parser(
        "merge-tasks",
        help="Merge a dropped split goal into a kept goal",
        description="Recombine mistakenly split goal history into one kept goal.",
    )
    merge_parser.add_argument("--keep-task-id", required=True, help="Goal that should remain after the merge")
    merge_parser.add_argument("--drop-task-id", required=True, help="Goal that should be merged into the kept goal")
    _add_report_output_flags(merge_parser)

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
    render_html_parser.add_argument("--days", type=int, default=None, metavar="N", help="Limit the time window to the last N days")
    # Default is empty so handle_render_html falls back to the
    # metrics-path-adjacent default warehouse (derived per call in commands.py).
    render_html_parser.add_argument("--warehouse-path", default="", help="SQLite warehouse path (default: derived from --metrics-path)")
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


def _hide_advanced_commands_from_help(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Drop advanced / pipeline-internal commands from the top-level `--help` listing.

    The commands remain callable and `<cmd> --help` still renders their
    per-command help. The epilog lists them by name so users know they exist.
    This mutates a private argparse attribute (stable across Py 3.9–3.13)
    because argparse has no public API to mark a subparser as hidden after
    creation.
    """
    # pylint: disable=protected-access
    subparsers._choices_actions = [  # noqa: SLF001
        act for act in subparsers._choices_actions
        if act.dest not in _HIDDEN_FROM_TOPLEVEL_HELP
    ]


def build_parser() -> argparse.ArgumentParser:
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
            '  %(prog)s start-task --title "Add CSV import" --task-type product\n'
            '  %(prog)s continue-task --task-id 2026-03-29-001 --notes "Retry after validation failure"\n'
            '  %(prog)s finish-task --task-id 2026-03-29-001 --status success --notes "Validated"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        # A short placeholder keeps the `usage:` header readable — argparse
        # would otherwise dump all 26 choice names in a single unwrapped blob.
        metavar="<command>",
    )
    _add_init_and_bootstrap_parsers(subparsers)
    _add_task_workflow_parsers(subparsers)
    _add_history_parsers(subparsers)
    _add_sync_and_render_parsers(subparsers)
    _hide_advanced_commands_from_help(subparsers)
    return parser
