from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_metrics.history_audit import audit_history, render_audit_report


def test_audit_history_flags_explicit_fail_as_likely_miss() -> None:
    report = audit_history(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Failed goal",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "fail",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": "unclear_task",
                    "notes": "Did not match requested outcome.",
                }
            ]
        }
    )

    assert len(report.candidates) == 1
    candidate = report.candidates[0]
    assert candidate.category == "likely_miss"
    assert candidate.goal_id == "goal-1"
    assert candidate.suggested_result_fit == "miss"


def test_audit_history_flags_superseded_success_as_partial_fit() -> None:
    report = audit_history(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Original goal",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "fail",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": "unclear_task",
                    "notes": "Not accepted.",
                },
                {
                    "goal_id": "goal-2",
                    "title": "Replacement goal",
                    "goal_type": "product",
                    "supersedes_goal_id": "goal-1",
                    "status": "success",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:06:00+00:00",
                    "finished_at": "2026-03-29T09:10:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": "Recovered in a follow-up goal.",
                },
            ]
        }
    )

    partial_candidates = [candidate for candidate in report.candidates if candidate.category == "likely_partial_fit"]
    assert len(partial_candidates) == 1
    candidate = partial_candidates[0]
    assert candidate.goal_id == "goal-2"
    assert candidate.related_goal_id == "goal-1"
    assert candidate.suggested_result_fit == "partial_fit"


def test_audit_history_flags_multi_attempt_success_as_partial_fit() -> None:
    report = audit_history(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Eventually worked",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 3,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:10:00+00:00",
                    "cost_usd": 0.2,
                    "tokens_total": 500,
                    "failure_reason": None,
                    "notes": "Needed several implementation passes.",
                }
            ]
        }
    )

    assert report.candidates[0].category == "likely_partial_fit"
    assert report.candidates[0].reason == "success required 3 attempts"


def test_audit_history_flags_stale_in_progress_goals() -> None:
    report = audit_history(
        {
            "goals": [
                {
                    "goal_id": "goal-open",
                    "title": "Still open",
                    "goal_type": "meta",
                    "supersedes_goal_id": None,
                    "status": "in_progress",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": None,
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                },
                {
                    "goal_id": "goal-closed",
                    "title": "Closed later",
                    "goal_type": "meta",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 1,
                    "started_at": "2026-03-29T10:00:00+00:00",
                    "finished_at": "2026-03-29T10:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                },
            ]
        }
    )

    stale_candidates = [candidate for candidate in report.candidates if candidate.category == "stale_in_progress"]
    assert len(stale_candidates) == 1
    assert stale_candidates[0].goal_id == "goal-open"


def test_audit_history_flags_low_cost_coverage_for_successful_product_goals() -> None:
    report = audit_history(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Product goal without cost",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                }
            ]
        }
    )

    low_cost_candidates = [candidate for candidate in report.candidates if candidate.category == "low_cost_coverage"]
    assert len(low_cost_candidates) == 1
    assert low_cost_candidates[0].goal_id == "goal-1"


def test_render_audit_report_groups_candidates() -> None:
    report = audit_history(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Failed goal",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "fail",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": "unclear_task",
                    "notes": None,
                },
                {
                    "goal_id": "goal-2",
                    "title": "Success without cost",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 1,
                    "started_at": "2026-03-29T10:00:00+00:00",
                    "finished_at": "2026-03-29T10:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                },
            ]
        }
    )

    rendered = render_audit_report(report)

    assert "Audit candidates" in rendered
    assert "[likely_miss]" in rendered
    assert "suggested_result_fit: miss" in rendered
    assert "[low_cost_coverage]" in rendered


def test_render_audit_report_for_empty_history_is_concise() -> None:
    rendered = render_audit_report(audit_history({"goals": []}))
    assert "_No suspicious history patterns found._" in rendered
