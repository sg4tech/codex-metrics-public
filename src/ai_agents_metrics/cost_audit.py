"""Audit which closed product goals have missing/partial cost coverage and why."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ai_agents_metrics.domain import GoalRecord, goal_from_dict

if TYPE_CHECKING:
    from datetime import datetime


def _ts_str(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

AUDIT_CATEGORY_ORDER = (
    "sync_gap",
    "partial_stored_coverage",
    "thread_unresolved",
    "no_usage_data_found",
    "telemetry_unavailable",
    "incomplete_goal_window",
)


# CostAuditCandidate is a canonical audit-record schema whose fields are
# consumed field-by-field by JSON/text renderers and tests — compressing the
# schema into nested structs would break the rendered output contract.
@dataclass(frozen=True)
class CostAuditCandidate:  # pylint: disable=too-many-instance-attributes
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


class UsageResolver(Protocol):
    """Keyword-only callable used to resolve Codex/Claude usage for an audit window."""

    # pylint: disable-next=too-many-arguments
    def __call__(
        self,
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> tuple[float | None, int | None]: ...


@dataclass(frozen=True)
class CostAuditContext:
    """Bundle of paths and resolver callables shared by every audit call.

    Grouped so `_classify_goal_cost_coverage` and `audit_cost_coverage` stay
    below pylint's too-many-arguments threshold.
    """

    pricing_path: Path
    codex_state_path: Path
    codex_logs_path: Path
    claude_root: Path
    cwd: Path
    codex_thread_id: str | None
    find_thread_id: ThreadResolver
    resolve_usage_window: UsageResolver


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
        started_at=_ts_str(goal.started_at),
        finished_at=_ts_str(goal.finished_at),
        has_cost=goal.cost_usd is not None,
        has_tokens=goal.tokens_total is not None,
        suggested_next_action=suggested_next_action,
    )


def _classify_goal_cost_coverage(
    goal: GoalRecord,
    *,
    context: CostAuditContext,
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
        if not (context.claude_root / "projects").exists():
            return _build_candidate(
                goal,
                category="telemetry_unavailable",
                reason="Claude Code telemetry directory (claude_root/projects) is unavailable for cost recovery",
                suggested_next_action="Ensure ~/.claude/projects/ exists and contains session JSONL files.",
            )
        # No thread resolution for Claude — lookup is by directory, not SQLite row.
        recovered_cost_usd, recovered_total_tokens = context.resolve_usage_window(
            state_path=context.claude_root,
            logs_path=context.codex_logs_path,  # unused for Claude, passed for interface compatibility
            cwd=context.cwd,
            started_at=_ts_str(goal.started_at),
            finished_at=_ts_str(goal.finished_at),
            pricing_path=context.pricing_path,
            thread_id=None,
            agent_name=goal.agent_name,
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

    if not context.codex_state_path.exists() or not context.codex_logs_path.exists():
        return _build_candidate(
            goal,
            category="telemetry_unavailable",
            reason="Codex state/log telemetry files are unavailable for recovery",
            suggested_next_action="Provide the correct Codex state/log paths before expecting automatic cost recovery.",
        )

    resolved_thread_id = context.find_thread_id(
        context.codex_state_path, context.cwd, context.codex_thread_id
    )
    if resolved_thread_id is None:
        return _build_candidate(
            goal,
            category="thread_unresolved",
            reason="no Codex thread could be resolved for the goal under current thread-matching rules",
            suggested_next_action="Run the goal closer to the actual Codex thread or pass an explicit --codex-thread-id when syncing.",
        )

    recovered_cost_usd, recovered_total_tokens = context.resolve_usage_window(
        state_path=context.codex_state_path,
        logs_path=context.codex_logs_path,
        cwd=context.cwd,
        started_at=_ts_str(goal.started_at),
        finished_at=_ts_str(goal.finished_at),
        pricing_path=context.pricing_path,
        thread_id=context.codex_thread_id,
        agent_name=goal.agent_name,
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
    context: CostAuditContext,
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
        for candidate in [_classify_goal_cost_coverage(goal, context=context)]
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


def render_cost_audit_report_json(report: CostAuditReport) -> str:
    return json.dumps({
        "covered_goals": report.covered_goals,
        "candidate_count": len(report.candidates),
        "candidates": [
            {
                "category": c.category,
                "goal_id": c.goal_id,
                "goal_type": c.goal_type,
                "status": c.status,
                "title": c.title,
                "reason": c.reason,
                "started_at": c.started_at,
                "finished_at": c.finished_at,
                "has_cost": c.has_cost,
                "has_tokens": c.has_tokens,
                "suggested_next_action": c.suggested_next_action,
            }
            for c in report.candidates
        ],
    })
