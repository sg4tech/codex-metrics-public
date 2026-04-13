"""Argument parser for the ai-agents-metrics CLI."""
from __future__ import annotations

import argparse
from pathlib import Path

from ai_agents_metrics import __version__
from ai_agents_metrics.domain import (
    ALLOWED_FAILURE_REASONS,
    ALLOWED_RESULT_FITS,
    ALLOWED_STATUSES,
    ALLOWED_TASK_TYPES,
)
from ai_agents_metrics.history.ingest import default_raw_warehouse_path

_METRICS_JSON_PATH = Path("metrics/events.ndjson")
_REPORT_MD_PATH = Path("docs/ai-agents-metrics.md")
_REPORT_HTML_PATH = Path("reports/report.html")
_CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
_CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
_CLAUDE_ROOT = Path.home() / ".claude"
_RAW_WAREHOUSE_PATH = default_raw_warehouse_path(_METRICS_JSON_PATH)
_PUBLIC_BOUNDARY_RULES_PATH = Path("config/public-boundary-rules.toml")
_SECURITY_RULES_PATH = Path("config/security-rules.toml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze your AI agent work history, track spending, and optimize your workflow. Point it at your history files and see retry pressure, token cost, and session timeline — no manual setup required.",
        epilog=(
            "Examples:\n"
            "  %(prog)s start-task --title \"Add CSV import\" --task-type product\n"
            "  %(prog)s continue-task --task-id 2026-03-29-001 --notes \"Retry after validation failure\"\n"
            "  %(prog)s finish-task --task-id 2026-03-29-001 --status success --notes \"Validated\"\n"
            "  %(prog)s update --title \"Add CSV import\" --task-type product --attempts-delta 1\n"
            "  %(prog)s update --task-id 2026-03-29-001 --status success --notes \"Validated\"\n"
            "  %(prog)s update --task-id 2026-03-29-002 --title \"Retry CSV import\" --task-type product --supersedes-task-id 2026-03-29-001 --status success\n"
            "  %(prog)s ensure-active-task\n"
            "  %(prog)s history-ingest --source-root ~/.codex\n"
            "  %(prog)s history-normalize\n"
            "  %(prog)s history-derive\n"
            "  %(prog)s audit-cost-coverage\n"
            "  %(prog)s sync-usage\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create the metrics JSON source of truth",
        description=(
            "Create the low-level metrics source of truth file. "
            "Use --write-report when you also want a markdown export."
        ),
    )
    init_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    init_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
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
    bootstrap_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    bootstrap_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
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
    start_parser.add_argument("--codex-state-path", default=str(_CODEX_STATE_PATH))
    start_parser.add_argument("--codex-logs-path", default=str(_CODEX_LOGS_PATH))
    start_parser.add_argument("--codex-thread-id")
    start_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))
    start_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    start_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
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
    continue_parser.add_argument("--codex-state-path", default=str(_CODEX_STATE_PATH))
    continue_parser.add_argument("--codex-logs-path", default=str(_CODEX_LOGS_PATH))
    continue_parser.add_argument("--codex-thread-id")
    continue_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))
    continue_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    continue_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
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
    finish_parser.add_argument("--codex-state-path", default=str(_CODEX_STATE_PATH))
    finish_parser.add_argument("--codex-logs-path", default=str(_CODEX_LOGS_PATH))
    finish_parser.add_argument("--codex-thread-id")
    finish_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))
    finish_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    finish_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
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
    update_parser.add_argument("--codex-state-path", default=str(_CODEX_STATE_PATH))
    update_parser.add_argument("--codex-logs-path", default=str(_CODEX_LOGS_PATH))
    update_parser.add_argument("--codex-thread-id")
    update_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))
    update_parser.add_argument("--failure-reason", choices=sorted(ALLOWED_FAILURE_REASONS), help="Primary failure reason for a failed goal")
    update_parser.add_argument(
        "--result-fit",
        choices=sorted(ALLOWED_RESULT_FITS),
        help="Operator quality judgement for closed product goals: exact_fit, partial_fit, or miss",
    )
    update_parser.add_argument("--notes", help="Optional note recorded on the goal and latest attempt entry")
    update_parser.add_argument("--started-at", help="Explicit ISO8601 start timestamp")
    update_parser.add_argument("--finished-at", help="Explicit ISO8601 finish timestamp")
    update_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    update_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
    update_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    show_parser = subparsers.add_parser(
        "show",
        help="Print current summary and operator review",
        description="Print the current summary, cost coverage, and operator review.",
    )
    show_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    show_parser.add_argument(
        "--warehouse-path",
        default=str(_RAW_WAREHOUSE_PATH),
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
    audit_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))

    compare_parser = subparsers.add_parser(
        "history-compare",
        help="Compare the structured metrics ledger against reconstructed agent history",
        description=(
            "Read the metrics source of truth and a derived agent history warehouse, then print an "
            "aggregate comparison for the current repository cwd."
        ),
    )
    compare_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    compare_parser.add_argument("--warehouse-path", default=str(_RAW_WAREHOUSE_PATH))
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
        default=str(_RAW_WAREHOUSE_PATH),
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
        default=str(_RAW_WAREHOUSE_PATH),
        help="SQLite warehouse path that already contains raw imported data",
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
        default=str(_RAW_WAREHOUSE_PATH),
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
        default=str(_RAW_WAREHOUSE_PATH),
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
    retro_timeline_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    retro_timeline_parser.add_argument("--warehouse-path", default=str(_RAW_WAREHOUSE_PATH))
    retro_timeline_parser.add_argument("--cwd", default=str(Path.cwd()))
    retro_timeline_parser.add_argument("--window-size", type=int, default=5)

    cost_audit_parser = subparsers.add_parser(
        "audit-cost-coverage",
        help="Explain why product goals are missing cost coverage",
        description=(
            "Inspect closed product goals and explain why cost coverage is missing, partial, or recoverable."
        ),
    )
    cost_audit_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    cost_audit_parser.add_argument("--pricing-path", default=None)
    cost_audit_parser.add_argument("--codex-state-path", default=str(_CODEX_STATE_PATH))
    cost_audit_parser.add_argument("--codex-logs-path", default=str(_CODEX_LOGS_PATH))
    cost_audit_parser.add_argument("--codex-thread-id")
    cost_audit_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))

    public_boundary_parser = subparsers.add_parser(
        "verify-public-boundary",
        help="Verify that a public repository tree does not contain private-only material",
        description=(
            "Check a candidate public repository tree against explicit public-boundary rules. "
            "Fail on forbidden paths, forbidden file types, unexpected roots, or private-content markers."
        ),
    )
    public_boundary_parser.add_argument("--repo-root", default=".")
    public_boundary_parser.add_argument("--rules-path", default=str(_PUBLIC_BOUNDARY_RULES_PATH))

    security_parser = subparsers.add_parser(
        "security",
        help="Run a fast staged-file security scan",
        description=(
            "Scan staged changes for secrets, token patterns, private keys, and other dangerous data "
            "before it lands in git."
        ),
    )
    security_parser.add_argument("--repo-root", default=".")
    security_parser.add_argument("--rules-path", default=str(_SECURITY_RULES_PATH))

    subparsers.add_parser(
        "ensure-active-task",
        help="Recover or verify active task bookkeeping from local git changes",
        description=(
            "Inspect the current git working tree for meaningful repository work and ensure that active task "
            "bookkeeping exists. If work has started without an active goal, create a recovery draft."
        ),
    ).add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))

    sync_parser = subparsers.add_parser(
        "sync-usage",
        help="Backfill usage and cost from local agent logs",
        description="Backfill known cost and token totals from local agent telemetry.",
    )
    sync_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    sync_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
    sync_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    sync_parser.add_argument("--pricing-path", default=None)
    sync_parser.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(_CODEX_STATE_PATH))
    sync_parser.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(_CODEX_LOGS_PATH))
    sync_parser.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
    sync_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))

    sync_legacy_parser = subparsers.add_parser(
        "sync-codex-usage",
        help="Deprecated alias for sync-usage",
        description="Backfill known cost and token totals from local agent telemetry.",
    )
    sync_legacy_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    sync_legacy_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
    sync_legacy_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")
    sync_legacy_parser.add_argument("--pricing-path", default=None)
    sync_legacy_parser.add_argument("--usage-state-path", "--codex-state-path", dest="usage_state_path", default=str(_CODEX_STATE_PATH))
    sync_legacy_parser.add_argument("--usage-logs-path", "--codex-logs-path", dest="usage_logs_path", default=str(_CODEX_LOGS_PATH))
    sync_legacy_parser.add_argument("--usage-thread-id", "--codex-thread-id", dest="usage_thread_id")
    sync_legacy_parser.add_argument("--claude-root", default=str(_CLAUDE_ROOT))

    merge_parser = subparsers.add_parser(
        "merge-tasks",
        help="Merge a dropped split goal into a kept goal",
        description="Recombine mistakenly split goal history into one kept goal.",
    )
    merge_parser.add_argument("--keep-task-id", required=True, help="Goal that should remain after the merge")
    merge_parser.add_argument("--drop-task-id", required=True, help="Goal that should be merged into the kept goal")
    merge_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    merge_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))
    merge_parser.add_argument("--write-report", action="store_true", help="Also render the optional markdown report")

    render_report_parser = subparsers.add_parser(
        "render-report",
        help="Render the optional markdown report from stored metrics",
        description="Generate docs/ai-agents-metrics.md on demand from the JSON source of truth.",
    )
    render_report_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    render_report_parser.add_argument("--report-path", default=str(_REPORT_MD_PATH))

    render_html_parser = subparsers.add_parser(
        "render-html",
        help="Render a self-contained HTML report with trend charts",
        description="Generate a static HTML file with four trend charts for human review.",
    )
    render_html_parser.add_argument("--metrics-path", default=str(_METRICS_JSON_PATH))
    render_html_parser.add_argument(
        "--output",
        default=str(_REPORT_HTML_PATH),
        help="Output path for the HTML file (default: reports/report.html)",
    )
    render_html_parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help="Limit the time window to the last N days",
    )

    return parser
