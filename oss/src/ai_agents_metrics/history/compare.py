from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_agents_metrics.domain import build_effective_goals, goal_from_dict
from ai_agents_metrics.history.compare_store import (
    HistoryCompareProjectRow,
    HistoryCompareScopeRow,
    HistoryCompareWarehouseData,
    load_history_compare_warehouse_data,
)


@dataclass(frozen=True)
class HistorySignals:
    """History-derived retry and coverage signals for a project, read from the warehouse."""

    project_threads: int
    retry_threads: int
    retry_rate: float
    ledger_goal_alignments: int
    ledger_goals_total: int
    is_all_projects: bool = False


def read_history_signals(
    warehouse_path: Path,
    project_cwd: Path,
    data: dict[str, Any],
) -> HistorySignals | None:
    """Read history-derived retry signals for the current project from the warehouse.

    Returns ``None`` when the warehouse does not exist or does not contain derived data,
    so callers can degrade gracefully to ledger-only display.

    Project-level stats are read from ``derived_projects`` filtered by ``parent_project_cwd``
    (which collapses Claude Code worktrees into the parent project).  Per-goal alignment
    counts how many closed ledger goals with known ``started_at``/``finished_at`` timestamps
    have at least one matching history thread in their time window.
    """
    if not warehouse_path.exists():
        return None

    cwd_str = str(project_cwd.resolve())
    worktree_prefix = cwd_str + "/.claude/worktrees/%"

    try:
        with sqlite3.connect(warehouse_path) as conn:
            conn.row_factory = sqlite3.Row
            # Confirm derived data is present
            try:
                conn.execute("SELECT 1 FROM derived_goals LIMIT 1").fetchone()
            except sqlite3.OperationalError:
                return None

            # Project-level: sum across all rows whose parent_project_cwd matches.
            # Falls back to project_cwd match for older warehouses without the column.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(derived_projects)").fetchall()}
            if "parent_project_cwd" in columns:
                row = conn.execute(
                    """
                    SELECT
                        coalesce(sum(thread_count), 0)       AS thread_count,
                        coalesce(sum(retry_thread_count), 0) AS retry_thread_count
                    FROM derived_projects
                    WHERE parent_project_cwd = ?
                    """,
                    (cwd_str,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT
                        coalesce(sum(thread_count), 0)       AS thread_count,
                        coalesce(sum(retry_thread_count), 0) AS retry_thread_count
                    FROM derived_projects
                    WHERE project_cwd = ?
                    """,
                    (cwd_str,),
                ).fetchone()

            project_threads = int(row["thread_count"])
            retry_threads = int(row["retry_thread_count"])
            is_all_projects = False

            # Fallback: if no threads match the current cwd, show all projects.
            if project_threads == 0:
                row = conn.execute(
                    """
                    SELECT
                        coalesce(sum(thread_count), 0)       AS thread_count,
                        coalesce(sum(retry_thread_count), 0) AS retry_thread_count
                    FROM derived_projects
                    """,
                ).fetchone()
                project_threads = int(row["thread_count"])
                retry_threads = int(row["retry_thread_count"])
                if project_threads > 0:
                    is_all_projects = True

            retry_rate = (retry_threads / project_threads) if project_threads > 0 else 0.0

            # Per-goal alignment: count ledger goals that have a matching history thread
            # in their started_at..finished_at window.
            goal_records = [goal_from_dict(g) for g in data.get("goals", [])]
            effective_goals = build_effective_goals(goal_records)
            closed_goals = [g for g in effective_goals if g.status in {"success", "fail"}]
            alignable = [g for g in closed_goals if g.started_at and g.finished_at]

            aligned_count = 0
            for goal in alignable:
                matched = conn.execute(
                    """
                    SELECT 1 FROM derived_goals
                    WHERE (cwd = ? OR cwd LIKE ?)
                      AND first_seen_at <= ?
                      AND last_seen_at  >= ?
                    LIMIT 1
                    """,
                    (cwd_str, worktree_prefix, goal.finished_at, goal.started_at),
                ).fetchone()
                if matched:
                    aligned_count += 1

    except sqlite3.DatabaseError:
        return None

    return HistorySignals(
        project_threads=project_threads,
        retry_threads=retry_threads,
        retry_rate=retry_rate,
        ledger_goal_alignments=aligned_count,
        ledger_goals_total=len(closed_goals),
        is_all_projects=is_all_projects,
    )


@dataclass(frozen=True)
class WarehouseScopeSummary:
    projects: int
    threads: int
    attempts: int
    retry_threads: int
    transcript_threads: int
    usage_threads: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class WarehouseProjectSummary:
    project_cwd: str
    threads: int
    attempts: int
    retry_threads: int
    message_count: int
    usage_event_count: int
    log_count: int
    timeline_event_count: int
    total_tokens: int | None


@dataclass(frozen=True)
class HistoryCompareFinding:
    category: str
    message: str


# HistoryCompareReport aggregates counts and summaries over the ledger and
# warehouse side-by-side. Each field is surfaced directly in rendered output,
# so grouping into nested structs would break the report contract.
@dataclass(frozen=True)
class HistoryCompareReport:  # pylint: disable=too-many-instance-attributes
    metrics_path: Path
    warehouse_path: Path
    cwd: Path
    ledger_goal_count: int
    ledger_closed_goal_count: int
    ledger_success_count: int
    ledger_fail_count: int
    ledger_attempts_total: int
    ledger_attempts_gt_one: int
    ledger_known_token_successes: int
    ledger_known_breakdown_successes: int
    ledger_total_tokens_known: int
    warehouse_global: WarehouseScopeSummary
    warehouse_project: WarehouseScopeSummary
    warehouse_projects: list[WarehouseProjectSummary]
    findings: list[HistoryCompareFinding]


def _scope_summary_from_row(row: HistoryCompareScopeRow) -> WarehouseScopeSummary:
    return WarehouseScopeSummary(
        projects=row.projects,
        threads=row.threads,
        attempts=row.attempts,
        retry_threads=row.retry_threads,
        transcript_threads=row.transcript_threads,
        usage_threads=row.usage_threads,
        input_tokens=row.input_tokens,
        cached_input_tokens=row.cached_input_tokens,
        output_tokens=row.output_tokens,
        total_tokens=row.total_tokens,
    )


def _project_summary_from_row(row: HistoryCompareProjectRow) -> WarehouseProjectSummary:
    return WarehouseProjectSummary(
        project_cwd=row.project_cwd,
        threads=row.threads,
        attempts=row.attempts,
        retry_threads=row.retry_threads,
        message_count=row.message_count,
        usage_event_count=row.usage_event_count,
        log_count=row.log_count,
        timeline_event_count=row.timeline_event_count,
        total_tokens=row.total_tokens,
    )


def _findings_from_data(
    *,
    warehouse_project: WarehouseScopeSummary,
    closed_goals: list[Any],
    successful_goals: list[Any],
    attempts_gt_one: list[Any],
    known_breakdown_successes: list[Any],
) -> list[HistoryCompareFinding]:
    findings: list[HistoryCompareFinding] = []
    if warehouse_project.threads == 0:
        findings.append(
            HistoryCompareFinding(
                category="missing_project_slice",
                message="The warehouse does not contain any derived history rows for the current repository cwd.",
            )
        )
        return findings

    if warehouse_project.threads < len(closed_goals):
        findings.append(
            HistoryCompareFinding(
                category="subset_scope",
                message=(
                    f"The reconstructed project slice currently covers {warehouse_project.threads} history threads, "
                    f"while the ledger has {len(closed_goals)} closed goals, so the warehouse is still a local subset view."
                ),
            )
        )
    if warehouse_project.retry_threads == 0 and attempts_gt_one:
        findings.append(
            HistoryCompareFinding(
                category="retry_mismatch",
                message=(
                    f"The current project slice shows 0 retry threads, while the ledger has {len(attempts_gt_one)} "
                    "closed goals with attempts > 1, so retry history is either outside the observed local slice or "
                    "not yet mapped one-to-one into reconstructed goals."
                ),
            )
        )
    if warehouse_project.usage_threads > 0 and len(known_breakdown_successes) < len(successful_goals):
        findings.append(
            HistoryCompareFinding(
                category="breakdown_gap",
                message=(
                    f"The warehouse has token totals on {warehouse_project.usage_threads}/{warehouse_project.threads} "
                    "project threads in the observed slice, while the ledger stores complete token breakdowns for only "
                    f"{len(known_breakdown_successes)}/{len(successful_goals)} successful goals."
                ),
            )
        )
    if warehouse_project.transcript_threads == warehouse_project.threads:
        findings.append(
            HistoryCompareFinding(
                category="transcript_strength",
                message=(
                    f"All {warehouse_project.transcript_threads} project threads in the observed slice have transcript messages, "
                    "so conversation-level analysis is available even where the ledger only stores final structured outcomes."
                ),
            )
        )
    return findings


def build_history_compare_report(
    data: dict[str, Any],
    *,
    warehouse_path: Path,
    cwd: Path,
    metrics_path: Path,
    warehouse_data: HistoryCompareWarehouseData,
) -> HistoryCompareReport:
    goal_records = [goal_from_dict(goal) for goal in data.get("goals", [])]
    effective_goals = build_effective_goals(goal_records)
    closed_goals = [goal for goal in effective_goals if goal.status in {"success", "fail"}]
    successful_goals = [goal for goal in closed_goals if goal.status == "success"]
    failed_goals = [goal for goal in closed_goals if goal.status == "fail"]
    attempts_gt_one = [goal for goal in closed_goals if goal.attempts > 1]
    known_token_successes = [goal for goal in successful_goals if goal.tokens_total_known is not None]
    known_breakdown_successes = [goal for goal in successful_goals if goal.token_breakdown_complete]
    ledger_total_tokens_known = sum(goal.tokens_total_known or 0 for goal in known_token_successes)

    findings = _findings_from_data(
        warehouse_project=_scope_summary_from_row(warehouse_data.project_scope),
        closed_goals=closed_goals,
        successful_goals=successful_goals,
        attempts_gt_one=attempts_gt_one,
        known_breakdown_successes=known_breakdown_successes,
    )

    return HistoryCompareReport(
        metrics_path=metrics_path,
        warehouse_path=warehouse_path,
        cwd=cwd.resolve(),
        ledger_goal_count=len(goal_records),
        ledger_closed_goal_count=len(closed_goals),
        ledger_success_count=len(successful_goals),
        ledger_fail_count=len(failed_goals),
        ledger_attempts_total=sum(goal.attempts for goal in closed_goals),
        ledger_attempts_gt_one=len(attempts_gt_one),
        ledger_known_token_successes=len(known_token_successes),
        ledger_known_breakdown_successes=len(known_breakdown_successes),
        ledger_total_tokens_known=ledger_total_tokens_known,
        warehouse_global=_scope_summary_from_row(warehouse_data.global_scope),
        warehouse_project=_scope_summary_from_row(warehouse_data.project_scope),
        warehouse_projects=[_project_summary_from_row(row) for row in warehouse_data.projects],
        findings=findings,
    )


def compare_metrics_to_history(
    data: dict[str, Any],
    *,
    warehouse_path: Path,
    cwd: Path,
    metrics_path: Path,
) -> HistoryCompareReport:
    warehouse_data = load_history_compare_warehouse_data(warehouse_path=warehouse_path, cwd=cwd)
    return build_history_compare_report(
        data,
        warehouse_path=warehouse_path,
        cwd=cwd,
        metrics_path=metrics_path,
        warehouse_data=warehouse_data,
    )


def render_history_compare_report(report: HistoryCompareReport) -> str:
    lines = [
        "Ledger vs History Compare",
        "",
        f"Metrics path: {report.metrics_path}",
        f"Warehouse path: {report.warehouse_path}",
        f"Repository cwd: {report.cwd}",
        "",
        "[ledger]",
        f"- goals: {report.ledger_goal_count}",
        f"- closed_goals: {report.ledger_closed_goal_count}",
        f"- successes: {report.ledger_success_count}",
        f"- fails: {report.ledger_fail_count}",
        f"- total_attempts: {report.ledger_attempts_total}",
        f"- closed_goals_with_attempts_gt_1: {report.ledger_attempts_gt_one}",
        f"- successful_goals_with_known_tokens: {report.ledger_known_token_successes}",
        f"- successful_goals_with_complete_breakdown: {report.ledger_known_breakdown_successes}",
        f"- known_total_tokens: {report.ledger_total_tokens_known}",
        "",
        "[warehouse_global]",
        f"- projects: {report.warehouse_global.projects}",
        f"- threads: {report.warehouse_global.threads}",
        f"- attempts: {report.warehouse_global.attempts}",
        f"- retry_threads: {report.warehouse_global.retry_threads}",
        f"- transcript_threads: {report.warehouse_global.transcript_threads}",
        f"- usage_threads: {report.warehouse_global.usage_threads}",
        f"- total_tokens: {report.warehouse_global.total_tokens}",
        "",
        "[warehouse_project]",
        f"- projects: {report.warehouse_project.projects}",
        f"- threads: {report.warehouse_project.threads}",
        f"- attempts: {report.warehouse_project.attempts}",
        f"- retry_threads: {report.warehouse_project.retry_threads}",
        f"- transcript_threads: {report.warehouse_project.transcript_threads}",
        f"- usage_threads: {report.warehouse_project.usage_threads}",
        f"- input_tokens: {report.warehouse_project.input_tokens}",
        f"- cached_input_tokens: {report.warehouse_project.cached_input_tokens}",
        f"- output_tokens: {report.warehouse_project.output_tokens}",
        f"- total_tokens: {report.warehouse_project.total_tokens}",
        "",
        "[warehouse_projects]",
    ]
    if not report.warehouse_projects:
        lines.append("- no project-level rollup rows available")
    else:
        for project in report.warehouse_projects:
            lines.append(
                f"- {project.project_cwd}: threads={project.threads}, attempts={project.attempts}, "
                f"retry_threads={project.retry_threads}, messages={project.message_count}, "
                f"usage_events={project.usage_event_count}, logs={project.log_count}, "
                f"timeline_events={project.timeline_event_count}, total_tokens={project.total_tokens}"
            )
    lines.extend([
        "",
        "[findings]",
    ])
    if not report.findings:
        lines.append("- no major aggregate mismatches detected")
    else:
        for finding in report.findings:
            lines.append(f"- {finding.category}: {finding.message}")
    return "\n".join(lines)


def render_history_compare_report_json(report: HistoryCompareReport) -> str:
    import json

    def _scope(s: WarehouseScopeSummary) -> dict[str, object]:
        return {
            "projects": s.projects,
            "threads": s.threads,
            "attempts": s.attempts,
            "retry_threads": s.retry_threads,
            "transcript_threads": s.transcript_threads,
            "usage_threads": s.usage_threads,
            "input_tokens": s.input_tokens,
            "cached_input_tokens": s.cached_input_tokens,
            "output_tokens": s.output_tokens,
            "total_tokens": s.total_tokens,
        }

    return json.dumps({
        "ledger": {
            "goal_count": report.ledger_goal_count,
            "closed_goal_count": report.ledger_closed_goal_count,
            "success_count": report.ledger_success_count,
            "fail_count": report.ledger_fail_count,
            "attempts_total": report.ledger_attempts_total,
            "attempts_gt_one": report.ledger_attempts_gt_one,
            "known_token_successes": report.ledger_known_token_successes,
            "known_breakdown_successes": report.ledger_known_breakdown_successes,
            "total_tokens_known": report.ledger_total_tokens_known,
        },
        "warehouse_global": _scope(report.warehouse_global),
        "warehouse_project": _scope(report.warehouse_project),
        "warehouse_projects": [
            {
                "project_cwd": p.project_cwd,
                "threads": p.threads,
                "attempts": p.attempts,
                "retry_threads": p.retry_threads,
                "message_count": p.message_count,
                "usage_event_count": p.usage_event_count,
                "log_count": p.log_count,
                "timeline_event_count": p.timeline_event_count,
                "total_tokens": p.total_tokens,
            }
            for p in report.warehouse_projects
        ],
        "findings": [
            {"category": f.category, "message": f.message}
            for f in report.findings
        ],
    })
