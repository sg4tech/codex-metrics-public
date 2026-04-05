from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from codex_metrics.domain import GoalRecord, goal_from_dict

AUDIT_CATEGORY_ORDER = (
    "sync_gap",
    "partial_stored_coverage",
    "thread_unresolved",
    "no_usage_data_found",
    "telemetry_unavailable",
    "incomplete_goal_window",
)


@dataclass(frozen=True)
class CostAuditCandidate:
    category: str
    goal_id: str
    goal_type: str
    status: str
    title: str
    reason: str
    started_at: str | None
    finished_at: str | None
    has_cost: bool
    has_tokens: bool
    suggested_next_action: str | None = None


@dataclass(frozen=True)
class CostAuditReport:
    covered_goals: int
    candidates: list[CostAuditCandidate]


ThreadResolver = Callable[[Path, Path, str | None], str | None]
UsageResolver = Callable[[Path, Path, Path, str | None, str | None, Path, str | None, str | None], tuple[float | None, int | None]]


def _build_candidate(
    goal: GoalRecord,
    *,
    category: str,
    reason: str,
    suggested_next_action: str | None,
) -> CostAuditCandidate:
    return CostAuditCandidate(
        category=category,
        goal_id=goal.goal_id,
        goal_type=goal.goal_type,
        status=goal.status,
        title=goal.title,
        reason=reason,
        started_at=goal.started_at,
        finished_at=goal.finished_at,
        has_cost=goal.cost_usd is not None,
        has_tokens=goal.tokens_total is not None,
        suggested_next_action=suggested_next_action,
    )


def _classify_goal_cost_coverage(
    goal: GoalRecord,
    *,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    claude_root: Path,
    cwd: Path,
    codex_thread_id: str | None,
    find_thread_id: ThreadResolver,
    resolve_usage_window: UsageResolver,
) -> CostAuditCandidate | None:
    has_cost = goal.cost_usd is not None
    has_tokens = goal.tokens_total is not None

    if has_cost and has_tokens:
        return None

    if has_cost != has_tokens:
        return _build_candidate(
            goal,
            category="partial_stored_coverage",
            reason="successful product goal stores only part of the expected cost signal",
            suggested_next_action="Inspect the goal record and re-run sync-usage if the missing field should be recoverable.",
        )

    if goal.started_at is None or goal.finished_at is None:
        return _build_candidate(
            goal,
            category="incomplete_goal_window",
            reason="goal is closed without a full started_at/finished_at window for cost recovery",
            suggested_next_action="Capture explicit goal boundaries before expecting automatic cost recovery.",
        )

    if goal.started_at == goal.finished_at:
        return _build_candidate(
            goal,
            category="incomplete_goal_window",
            reason="goal is closed with a zero-duration recovery window, which is usually too narrow for automatic cost capture",
            suggested_next_action="Start the goal before the real Codex work begins and close it after the work ends so usage falls inside the recorded window.",
        )

    is_claude_goal = goal.agent_name == "claude"

    if is_claude_goal:
        # Claude uses JSONL telemetry under claude_root/projects/, not Codex SQLite.
        if not (claude_root / "projects").exists():
            return _build_candidate(
                goal,
                category="telemetry_unavailable",
                reason="Claude Code telemetry directory (claude_root/projects) is unavailable for cost recovery",
                suggested_next_action="Ensure ~/.claude/projects/ exists and contains session JSONL files.",
            )
        # No thread resolution for Claude — lookup is by directory, not SQLite row.
        recovered_cost_usd, recovered_total_tokens = resolve_usage_window(
            claude_root,
            codex_logs_path,  # unused for Claude, passed for interface compatibility
            cwd,
            goal.started_at,
            goal.finished_at,
            pricing_path,
            None,
            goal.agent_name,
        )
        if recovered_cost_usd is None and recovered_total_tokens is None:
            return _build_candidate(
                goal,
                category="no_usage_data_found",
                reason="goal has a closed window but no recoverable Claude usage was found in the JSONL telemetry",
                suggested_next_action="Verify that Claude work actually occurred inside the recorded goal window.",
            )
        return _build_candidate(
            goal,
            category="sync_gap",
            reason="recoverable Claude usage exists for the goal window, but the stored goal still has no cost coverage",
            suggested_next_action="Run sync-usage or inspect why automatic usage recovery was skipped during update.",
        )

    if not codex_state_path.exists() or not codex_logs_path.exists():
        return _build_candidate(
            goal,
            category="telemetry_unavailable",
            reason="Codex state/log telemetry files are unavailable for recovery",
            suggested_next_action="Provide the correct Codex state/log paths before expecting automatic cost recovery.",
        )

    resolved_thread_id = find_thread_id(codex_state_path, cwd, codex_thread_id)
    if resolved_thread_id is None:
        return _build_candidate(
            goal,
            category="thread_unresolved",
            reason="no Codex thread could be resolved for the goal under current thread-matching rules",
            suggested_next_action="Run the goal closer to the actual Codex thread or pass an explicit --codex-thread-id when syncing.",
        )

    recovered_cost_usd, recovered_total_tokens = resolve_usage_window(
        codex_state_path,
        codex_logs_path,
        cwd,
        goal.started_at,
        goal.finished_at,
        pricing_path,
        codex_thread_id,
        goal.agent_name,
    )
    if recovered_cost_usd is None and recovered_total_tokens is None:
        return _build_candidate(
            goal,
            category="no_usage_data_found",
            reason="goal has a closed window and resolved thread, but no recoverable Codex usage was found",
            suggested_next_action="Verify that Codex work actually occurred inside the recorded goal window and under the tracked thread.",
        )

    return _build_candidate(
        goal,
        category="sync_gap",
        reason="recoverable Codex usage exists for the goal window, but the stored goal still has no cost coverage",
        suggested_next_action="Run sync-usage or inspect why automatic usage recovery was skipped during update.",
    )


def audit_cost_coverage(
    data: dict[str, Any],
    *,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    cwd: Path,
    claude_root: Path = Path.home() / ".claude",
    codex_thread_id: str | None,
    find_thread_id: ThreadResolver,
    resolve_usage_window: UsageResolver,
) -> CostAuditReport:
    goals = [goal_from_dict(goal) for goal in data.get("goals", [])]
    closed_product_goals = [
        goal
        for goal in goals
        if goal.goal_type == "product" and goal.status in {"success", "fail"}
    ]
    candidates = [
        candidate
        for goal in closed_product_goals
        for candidate in [
            _classify_goal_cost_coverage(
                goal,
                pricing_path=pricing_path,
                codex_state_path=codex_state_path,
                codex_logs_path=codex_logs_path,
                claude_root=claude_root,
                cwd=cwd,
                codex_thread_id=codex_thread_id,
                find_thread_id=find_thread_id,
                resolve_usage_window=resolve_usage_window,
            )
        ]
        if candidate is not None
    ]
    ordered_candidates = sorted(
        candidates,
        key=lambda candidate: (
            AUDIT_CATEGORY_ORDER.index(candidate.category),
            candidate.goal_id,
        ),
    )
    return CostAuditReport(
        covered_goals=len(closed_product_goals) - len(ordered_candidates),
        candidates=ordered_candidates,
    )


def render_cost_audit_report(report: CostAuditReport) -> str:
    if not report.candidates:
        return "Cost coverage audit\n\n_All closed product goals have stored cost and token coverage._"

    lines = [
        "Cost coverage audit",
        "",
        f"- Fully covered closed product goals: {report.covered_goals}",
        f"- Audit candidates: {len(report.candidates)}",
        "",
    ]
    current_category: str | None = None

    for candidate in report.candidates:
        if candidate.category != current_category:
            if current_category is not None:
                lines.append("")
            current_category = candidate.category
            lines.append(f"[{candidate.category}]")
        lines.append(f"- {candidate.goal_id} | {candidate.goal_type} | {candidate.status}")
        lines.append(f"  title: {candidate.title}")
        lines.append(f"  started_at: {candidate.started_at or 'n/a'}")
        lines.append(f"  finished_at: {candidate.finished_at or 'n/a'}")
        lines.append(f"  has_cost: {'yes' if candidate.has_cost else 'no'}")
        lines.append(f"  has_tokens: {'yes' if candidate.has_tokens else 'no'}")
        lines.append(f"  reason: {candidate.reason}")
        if candidate.suggested_next_action is not None:
            lines.append(f"  suggested_next_action: {candidate.suggested_next_action}")

    return "\n".join(lines)
