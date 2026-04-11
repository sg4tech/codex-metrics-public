from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ai_agents_metrics.domain import GoalRecord, goal_from_dict

AUDIT_CATEGORY_ORDER = (
    "likely_miss",
    "likely_partial_fit",
    "stale_in_progress",
    "low_cost_coverage",
)

PARTIAL_FIT_HINTS = (
    "retry",
    "not accepted",
    "partial",
    "missing",
    "unclear",
)


@dataclass(frozen=True)
class AuditCandidate:
    category: str
    goal_id: str
    goal_type: str
    status: str
    title: str
    reason: str
    suggested_result_fit: str | None = None
    related_goal_id: str | None = None


@dataclass(frozen=True)
class AuditReport:
    candidates: list[AuditCandidate]


def _contains_hint(text: str | None, hints: tuple[str, ...]) -> bool:
    if text is None:
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in hints)


def _goal_timestamp(goal: GoalRecord) -> datetime | None:
    return goal.finished_at or goal.started_at


def find_likely_miss_candidates(goals: list[GoalRecord]) -> list[AuditCandidate]:
    candidates: list[AuditCandidate] = []
    for goal in goals:
        if goal.status != "fail":
            continue
        if goal.result_fit is not None:
            continue
        reason = "explicit failed goal"
        if goal.failure_reason is not None:
            reason += f" with failure_reason={goal.failure_reason}"
        candidates.append(
            AuditCandidate(
                category="likely_miss",
                goal_id=goal.goal_id,
                goal_type=goal.goal_type,
                status=goal.status,
                title=goal.title,
                reason=reason,
                suggested_result_fit="miss",
            )
        )
    return candidates


def find_likely_partial_fit_candidates(goals: list[GoalRecord]) -> list[AuditCandidate]:
    goal_by_id = {goal.goal_id: goal for goal in goals}
    candidates: list[AuditCandidate] = []

    for goal in goals:
        if goal.goal_type != "product":
            continue
        if goal.status != "success":
            continue
        if goal.result_fit is not None:
            continue

        reason: str | None = None
        related_goal_id: str | None = None

        if goal.attempts > 1:
            reason = f"success required {goal.attempts} attempts"
        elif goal.supersedes_goal_id is not None:
            predecessor = goal_by_id.get(goal.supersedes_goal_id)
            related_goal_id = goal.supersedes_goal_id
            if predecessor is not None and predecessor.status == "fail":
                reason = f"supersedes failed goal {goal.supersedes_goal_id}"
            else:
                reason = f"supersedes prior goal {goal.supersedes_goal_id}"
        elif _contains_hint(goal.title, PARTIAL_FIT_HINTS) or _contains_hint(goal.notes, PARTIAL_FIT_HINTS):
            reason = "success record contains retry or correction hints"

        if reason is None:
            continue

        candidates.append(
            AuditCandidate(
                category="likely_partial_fit",
                goal_id=goal.goal_id,
                goal_type=goal.goal_type,
                status=goal.status,
                title=goal.title,
                reason=reason,
                suggested_result_fit="partial_fit",
                related_goal_id=related_goal_id,
            )
        )

    return candidates


def find_stale_in_progress_candidates(goals: list[GoalRecord]) -> list[AuditCandidate]:
    candidates: list[AuditCandidate] = []
    closed_goal_times = [
        timestamp
        for goal in goals
        if goal.status in {"success", "fail"}
        for timestamp in [_goal_timestamp(goal)]
        if timestamp is not None
    ]
    if not closed_goal_times:
        return candidates

    latest_closed_time = max(closed_goal_times)
    for goal in goals:
        if goal.status != "in_progress":
            continue
        goal_time = _goal_timestamp(goal)
        if goal_time is None:
            continue
        if goal_time >= latest_closed_time:
            continue
        candidates.append(
            AuditCandidate(
                category="stale_in_progress",
                goal_id=goal.goal_id,
                goal_type=goal.goal_type,
                status=goal.status,
                title=goal.title,
                reason="older open goal exists alongside newer closed goals",
            )
        )
    return candidates


def find_low_cost_coverage_candidates(goals: list[GoalRecord]) -> list[AuditCandidate]:
    candidates: list[AuditCandidate] = []
    for goal in goals:
        if goal.goal_type != "product" or goal.status != "success":
            continue
        if goal.cost_usd is not None or goal.tokens_total is not None:
            continue
        candidates.append(
            AuditCandidate(
                category="low_cost_coverage",
                goal_id=goal.goal_id,
                goal_type=goal.goal_type,
                status=goal.status,
                title=goal.title,
                reason="successful product goal has no known cost or token totals",
            )
        )
    return candidates


def audit_history(data: dict[str, Any]) -> AuditReport:
    goal_records = [goal_from_dict(goal) for goal in data.get("goals", [])]
    candidates = [
        *find_likely_miss_candidates(goal_records),
        *find_likely_partial_fit_candidates(goal_records),
        *find_stale_in_progress_candidates(goal_records),
        *find_low_cost_coverage_candidates(goal_records),
    ]
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            AUDIT_CATEGORY_ORDER.index(candidate.category),
            candidate.goal_id,
        ),
    )
    return AuditReport(candidates=ordered)


def render_audit_report(report: AuditReport) -> str:
    if not report.candidates:
        return "Audit candidates\n\n_No suspicious history patterns found._"

    lines = ["Audit candidates", ""]
    current_category: str | None = None

    for candidate in report.candidates:
        if candidate.category != current_category:
            if current_category is not None:
                lines.append("")
            current_category = candidate.category
            lines.append(f"[{candidate.category}]")
        lines.append(f"- {candidate.goal_id} | {candidate.goal_type} | {candidate.status}")
        lines.append(f"  title: {candidate.title}")
        lines.append(f"  reason: {candidate.reason}")
        if candidate.related_goal_id is not None:
            lines.append(f"  related_goal_id: {candidate.related_goal_id}")
        if candidate.suggested_result_fit is not None:
            lines.append(f"  suggested_result_fit: {candidate.suggested_result_fit}")

    return "\n".join(lines)


def render_audit_report_json(report: AuditReport) -> str:
    import json
    return json.dumps({
        "candidate_count": len(report.candidates),
        "candidates": [
            {
                "category": c.category,
                "goal_id": c.goal_id,
                "goal_type": c.goal_type,
                "status": c.status,
                "title": c.title,
                "reason": c.reason,
                "suggested_result_fit": c.suggested_result_fit,
                "related_goal_id": c.related_goal_id,
            }
            for c in report.candidates
        ],
    })
