from __future__ import annotations

import io
from unittest.mock import patch

from ai_agents_metrics import domain, reporting
from ai_agents_metrics.history.compare import HistorySignals


def _base_metrics() -> dict[str, object]:
    return {
        "summary": domain.empty_summary_block(include_by_task_type=True),
        "goals": [],
        "entries": [],
    }


def test_build_product_quality_summary_uses_effective_product_goals() -> None:
    data = _base_metrics()
    data["goals"] = [
        {
            "goal_id": "goal-a",
            "title": "Original miss",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "fail",
            "attempts": 1,
            "started_at": "2026-03-31T09:00:00+00:00",
            "finished_at": "2026-03-31T09:05:00+00:00",
            "cost_usd": None,
            "tokens_total": None,
            "failure_reason": "validation_failed",
            "notes": None,
            "result_fit": "miss",
        },
        {
            "goal_id": "goal-b",
            "title": "Recovered result",
            "goal_type": "product",
            "supersedes_goal_id": "goal-a",
            "status": "success",
            "attempts": 2,
            "started_at": "2026-03-31T09:06:00+00:00",
            "finished_at": "2026-03-31T09:10:00+00:00",
            "cost_usd": 0.5,
            "tokens_total": 500,
            "failure_reason": None,
            "notes": None,
            "result_fit": "partial_fit",
        },
        {
            "goal_id": "goal-c",
            "title": "Exact fit",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-31T10:00:00+00:00",
            "finished_at": "2026-03-31T10:05:00+00:00",
            "cost_usd": 1.0,
            "tokens_total": 1000,
            "failure_reason": None,
            "notes": None,
            "result_fit": "exact_fit",
        },
        {
            "goal_id": "retro-1",
            "title": "Retro",
            "goal_type": "retro",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-31T11:00:00+00:00",
            "finished_at": "2026-03-31T11:05:00+00:00",
            "cost_usd": 0.2,
            "tokens_total": 200,
            "failure_reason": None,
            "notes": None,
            "result_fit": None,
        },
    ]
    domain.recompute_summary(data)

    summary = reporting.build_product_quality_summary(data)

    assert summary.closed_product_goals == 2
    assert summary.successful_product_goals == 2
    assert summary.failed_product_goals == 0
    assert summary.reviewed_product_goals == 2
    assert summary.unreviewed_product_goals == 0
    assert summary.exact_fit_goals == 1
    assert summary.partial_fit_goals == 1
    assert summary.miss_goals == 0
    assert summary.review_coverage == 1.0
    assert summary.exact_fit_rate_reviewed == 0.5
    assert summary.attempts_per_closed_product_goal == 2.0
    assert summary.known_cost_successes == 2
    assert summary.known_cost_per_success_usd == 0.75
    assert summary.known_cost_per_success_tokens == 750.0


def test_build_product_quality_summary_excludes_failed_goal_cost_from_success_average() -> None:
    data = _base_metrics()
    data["goals"] = [
        {
            "goal_id": "goal-success",
            "title": "Successful goal",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-31T09:00:00+00:00",
            "finished_at": "2026-03-31T09:05:00+00:00",
            "cost_usd": 1.0,
            "tokens_total": 1000,
            "failure_reason": None,
            "notes": None,
            "result_fit": "exact_fit",
        },
        {
            "goal_id": "goal-fail",
            "title": "Failed goal",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "fail",
            "attempts": 1,
            "started_at": "2026-03-31T10:00:00+00:00",
            "finished_at": "2026-03-31T10:05:00+00:00",
            "cost_usd": 9.0,
            "tokens_total": 9000,
            "failure_reason": "validation_failed",
            "notes": None,
            "result_fit": "miss",
        },
    ]
    domain.recompute_summary(data)

    summary = reporting.build_product_quality_summary(data)

    assert summary.known_cost_successes == 1
    assert summary.known_token_successes == 1
    assert summary.known_cost_per_success_usd == 1.0
    assert summary.known_cost_per_success_tokens == 1000.0


def test_build_agent_recommendations_flags_partial_coverage_and_misses() -> None:
    recommendations = reporting.build_agent_recommendations(
        {
            "successes": 3,
            "known_cost_successes": 2,
            "known_cost_per_success_usd": 0.5,
            "complete_cost_successes": 1,
            "complete_cost_per_covered_success_usd": 0.5,
            "by_goal_type": {
                "product": {"closed_tasks": 4},
                "retro": {"closed_tasks": 0},
                "meta": {"closed_tasks": 5},
            },
            "entries": {
                "fails": 1,
                "failure_reasons": {"unclear_task": 1},
            },
        },
        reporting.ProductQualitySummary(
            closed_product_goals=4,
            successful_product_goals=3,
            failed_product_goals=1,
            reviewed_product_goals=2,
            unreviewed_product_goals=2,
            exact_fit_goals=1,
            partial_fit_goals=0,
            miss_goals=1,
            exact_fit_rate_reviewed=0.5,
            miss_rate_reviewed=0.5,
            review_coverage=0.5,
            attempts_per_closed_product_goal=1.25,
            known_cost_successes=2,
            known_token_successes=2,
            known_cost_per_success_usd=0.5,
            known_cost_per_success_tokens=500.0,
        ),
    )

    rendered = [reporting._format_recommendation(recommendation) for recommendation in recommendations]

    assert any("quality_review_coverage" in line for line in rendered)
    assert any("Backfill result_fit" in line or "Review unreviewed product goals" in line for line in rendered)
    assert any("quality_miss" in line for line in rendered)
    assert any("Inspect missed product goals first" in line for line in rendered)
    assert any("retry_pressure" in line for line in rendered)
    assert any("entry_failures" in line for line in rendered)


def test_generate_report_md_starts_with_product_quality_section() -> None:
    data = _base_metrics()
    data["goals"] = [
        {
            "goal_id": "goal-1",
            "title": "Exact fit goal",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-31T09:00:00+00:00",
            "finished_at": "2026-03-31T09:01:00+00:00",
            "cost_usd": 0.25,
            "tokens_total": 1000,
            "failure_reason": None,
            "notes": None,
            "result_fit": "exact_fit",
        }
    ]
    domain.recompute_summary(data)

    rendered = reporting.generate_report_md(data)

    assert "## Product quality" in rendered
    assert "## Agent recommendations" in rendered
    assert "## Operational summary" in rendered
    assert rendered.index("## Product quality") < rendered.index("## Operational summary")
    assert "- Reviewed result fit: 1/1 closed product goals" in rendered
    assert "- Exact Fit Rate (reviewed): 100.00%" in rendered
    assert "Next action:" in rendered


def test_generate_report_md_redacts_secret_like_notes_and_titles() -> None:
    data = _base_metrics()
    data["goals"] = [
        {
            "goal_id": "goal-1",
            "title": "Rotate token sk-test-secret-value-1234567890",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-31T09:00:00+00:00",
            "finished_at": "2026-03-31T09:01:00+00:00",
            "cost_usd": 0.25,
            "tokens_total": 1000,
            "failure_reason": None,
            "notes": "Bearer abcdefghijklmnop",
            "result_fit": "exact_fit",
        }
    ]
    domain.recompute_summary(data)

    rendered = reporting.generate_report_md(data)

    assert "sk-test-secret-value-1234567890" not in rendered
    assert "Bearer abcdefghijklmnop" not in rendered
    assert "[REDACTED]" in rendered


# print_summary — history signals section


def _capture_print_summary(history_signals: HistorySignals | None) -> str:
    data = {"summary": domain.empty_summary_block(include_by_task_type=True), "goals": [], "entries": []}
    domain.recompute_summary(data)
    buf = io.StringIO()
    with patch("builtins.print", side_effect=lambda *a, **_kw: buf.write(" ".join(str(x) for x in a) + "\n")):
        reporting.print_summary(data, history_signals)
    return buf.getvalue()


def test_print_summary_no_warehouse_shows_hint() -> None:
    output = _capture_print_summary(None)
    assert "History signals: not available" in output
    assert "history-update" in output


def test_print_summary_all_projects_scope_shows_tip() -> None:
    signals = HistorySignals(
        project_threads=10,
        retry_threads=2,
        retry_rate=0.2,
        ledger_goal_alignments=0,
        ledger_goals_total=0,
        is_all_projects=True,
    )
    output = _capture_print_summary(signals)
    assert "no history for current directory" in output
    assert "Tip:" in output
    assert "history-update" in output
    # Should not show per-goal alignment line for all-projects scope
    assert "Per-goal alignment" not in output


def test_print_summary_current_project_scope_no_tip() -> None:
    signals = HistorySignals(
        project_threads=5,
        retry_threads=1,
        retry_rate=0.2,
        ledger_goal_alignments=3,
        ledger_goals_total=4,
        is_all_projects=False,
    )
    output = _capture_print_summary(signals)
    assert "History signals (warehouse):" in output
    assert "no history for current directory" not in output
    assert "Per-goal alignment" in output
