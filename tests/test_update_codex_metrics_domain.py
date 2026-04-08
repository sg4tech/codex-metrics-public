from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_metrics.domain import (
    AttemptEntryRecord,
    EffectiveGoalRecord,
    GoalRecord,
    apply_attempt_usage_deltas,
    apply_goal_updates,
    build_effective_goals,
    compute_entry_summary,
    compute_numeric_delta,
    compute_summary_block,
    create_goal_record,
    ensure_goal_type_update_allowed,
    finalize_goal_update,
    next_goal_id,
    parse_iso_datetime,
    parse_iso_datetime_flexible,
    sync_goal_attempt_entries,
    update_latest_attempt_entry,
    validate_entry_record,
    validate_goal_record,
    validate_metrics_data,
)
from codex_metrics.reporting import build_operator_review

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_codex_metrics.py"
SPEC = importlib.util.spec_from_file_location("update_codex_metrics_module", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _ts(value: object) -> object:
    if isinstance(value, str):
        return parse_iso_datetime_flexible(value, "ts")
    return value


def make_goal_record(**overrides: object) -> object:
    values = {
        "goal_id": "goal-1",
        "title": "Goal",
        "goal_type": "product",
        "supersedes_goal_id": None,
        "status": "in_progress",
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
        "result_fit": None,
    }
    values.update(overrides)
    values["started_at"] = _ts(values["started_at"])
    values["finished_at"] = _ts(values["finished_at"])
    return GoalRecord(**values)


def make_effective_goal_record(**overrides: object) -> object:
    values = {
        "goal_id": "goal-1",
        "title": "Goal",
        "goal_type": "product",
        "status": "in_progress",
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "cost_usd_known": None,
        "cost_complete": False,
        "input_tokens": None,
        "input_tokens_known": None,
        "cached_input_tokens": None,
        "cached_input_tokens_known": None,
        "output_tokens": None,
        "output_tokens_known": None,
        "token_breakdown_complete": False,
        "tokens_total": None,
        "tokens_total_known": None,
        "tokens_complete": False,
        "failure_reason": None,
        "notes": None,
        "supersedes_goal_id": None,
        "result_fit": None,
    }
    values.update(overrides)
    values["started_at"] = _ts(values["started_at"])
    values["finished_at"] = _ts(values["finished_at"])
    return EffectiveGoalRecord(**values)


def make_attempt_entry_record(**overrides: object) -> object:
    values = {
        "entry_id": "goal-1-attempt-001",
        "goal_id": "goal-1",
        "entry_type": "product",
        "inferred": False,
        "status": "in_progress",
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
    }
    values.update(overrides)
    values["started_at"] = _ts(values["started_at"])
    values["finished_at"] = _ts(values["finished_at"])
    return AttemptEntryRecord(**values)


def make_goal_dict(**overrides: object) -> dict[str, object]:
    values = {
        "goal_id": "goal-1",
        "title": "Goal",
        "goal_type": "product",
        "supersedes_goal_id": None,
        "status": "in_progress",
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
        "result_fit": None,
    }
    values.update(overrides)
    return values


def make_entry_dict(**overrides: object) -> dict[str, object]:
    values = {
        "entry_id": "goal-1-attempt-001",
        "goal_id": "goal-1",
        "entry_type": "product",
        "inferred": False,
        "status": "in_progress",
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
    }
    values.update(overrides)
    return values


def test_compute_summary_block_uses_closed_goals_for_attempt_average() -> None:
    summary = compute_summary_block(
        [
            make_effective_goal_record(
                goal_id="goal-1",
                title="Goal one",
                status="success",
                attempts=2,
                cost_usd=0.5,
                cost_usd_known=0.5,
                cost_complete=True,
                tokens_total=500,
                tokens_total_known=500,
                tokens_complete=True,
            ),
            make_effective_goal_record(
                goal_id="goal-2",
                title="Goal two",
                status="fail",
                attempts=4,
                failure_reason="other",
            ),
        ]
    )

    assert summary["closed_tasks"] == 2
    assert summary["successes"] == 1
    assert summary["fails"] == 1
    assert summary["total_attempts"] == 6
    assert summary["success_rate"] == 0.5
    assert summary["attempts_per_closed_task"] == 3.0
    assert summary["known_cost_successes"] == 1
    assert summary["known_token_successes"] == 1
    assert summary["complete_cost_successes"] == 1
    assert summary["complete_token_successes"] == 1
    assert summary["known_cost_per_success_usd"] == 0.5
    assert summary["known_cost_per_success_tokens"] == 500.0
    assert summary["complete_cost_per_covered_success_usd"] == 0.5
    assert summary["complete_cost_per_covered_success_tokens"] == 500.0
    assert summary["cost_per_success_usd"] == 0.5
    assert summary["cost_per_success_tokens"] == 500.0


def test_compute_summary_block_separates_known_and_complete_cost_views() -> None:
    summary = compute_summary_block(
        [
            make_effective_goal_record(
                goal_id="goal-1",
                title="Goal one",
                status="success",
                attempts=1,
                cost_usd=0.5,
                cost_usd_known=0.5,
                cost_complete=True,
                tokens_total=500,
                tokens_total_known=500,
                tokens_complete=True,
            ),
            make_effective_goal_record(
                goal_id="goal-2",
                title="Goal two",
                status="success",
                attempts=2,
                cost_usd_known=1.0,
                tokens_total_known=1200,
            ),
        ]
    )

    assert summary["successes"] == 2
    assert summary["total_cost_usd"] == 1.5
    assert summary["total_tokens"] == 1700
    assert summary["known_cost_successes"] == 2
    assert summary["known_token_successes"] == 2
    assert summary["complete_cost_successes"] == 1
    assert summary["complete_token_successes"] == 1
    assert summary["known_cost_per_success_usd"] == 0.75
    assert summary["known_cost_per_success_tokens"] == 850.0
    assert summary["complete_cost_per_covered_success_usd"] == 0.5
    assert summary["complete_cost_per_covered_success_tokens"] == 500.0
    assert summary["cost_per_success_usd"] is None
    assert summary["cost_per_success_tokens"] is None


def test_compute_summary_block_tracks_model_coverage_and_mixed_goals() -> None:
    summary = compute_summary_block(
        [
            make_effective_goal_record(
                goal_id="goal-1",
                title="Goal one",
                status="success",
                attempts=1,
                cost_usd=0.5,
                cost_usd_known=0.5,
                cost_complete=True,
                tokens_total=500,
                tokens_total_known=500,
                tokens_complete=True,
                model="gpt-5",
                model_complete=True,
                model_consistent=True,
            ),
            make_effective_goal_record(
                goal_id="goal-2",
                title="Goal two",
                status="fail",
                attempts=2,
                failure_reason="other",
                model=None,
                model_complete=True,
                model_consistent=False,
            ),
        ]
    )

    assert summary["model_summary_goals"] == 1
    assert summary["model_complete_goals"] == 2
    assert summary["mixed_model_goals"] == 1


def test_build_effective_goals_merges_superseded_chain_attempts_and_known_cost() -> None:
    effective_goals = build_effective_goals(
        [
            make_goal_record(
                goal_id="goal-1",
                title="Original goal",
                status="fail",
                attempts=1,
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:05:00+00:00",
                failure_reason="validation_failed",
                notes="First attempt failed",
            ),
            make_goal_record(
                goal_id="goal-2",
                title="Replacement goal",
                supersedes_goal_id="goal-1",
                status="success",
                attempts=2,
                started_at="2026-03-29T09:06:00+00:00",
                finished_at="2026-03-29T09:10:00+00:00",
                cost_usd=0.25,
                tokens_total=1000,
                notes="Second chain succeeded",
            ),
        ]
    )

    assert len(effective_goals) == 1
    goal = effective_goals[0]
    assert goal.goal_id == "goal-2"
    assert goal.status == "success"
    assert goal.attempts == 3
    assert goal.started_at == parse_iso_datetime("2026-03-29T09:00:00+00:00", "started_at")
    assert goal.finished_at == parse_iso_datetime("2026-03-29T09:10:00+00:00", "finished_at")
    assert goal.cost_usd_known == 0.25
    assert goal.cost_usd is None
    assert goal.tokens_total_known == 1000
    assert goal.tokens_total is None


def test_compute_entry_summary_counts_failure_reasons_from_failed_entries_only() -> None:
    summary = compute_entry_summary(
        [
            make_attempt_entry_record(
                entry_id="entry-1",
                goal_id="goal-1",
                status="success",
                cost_usd=0.2,
                tokens_total=300,
            ),
            make_attempt_entry_record(
                entry_id="entry-2",
                goal_id="goal-1",
                status="fail",
                failure_reason="unclear_task",
            ),
            make_attempt_entry_record(
                entry_id="entry-3",
                goal_id="goal-2",
                inferred=True,
                status="fail",
            ),
        ]
    )

    assert summary["closed_entries"] == 3
    assert summary["successes"] == 1
    assert summary["fails"] == 2
    assert summary["success_rate"] == 1 / 3
    assert summary["total_cost_usd"] == 0.2
    assert summary["total_tokens"] == 300
    assert summary["failure_reasons"] == {"unclear_task": 1}


def test_build_operator_review_surfaces_agent_diagnoses() -> None:
    review = build_operator_review(
        {
            "successes": 3,
            "known_cost_successes": 1,
            "known_cost_per_success_usd": 0.25,
            "complete_cost_successes": 1,
            "complete_cost_per_covered_success_usd": 0.25,
            "by_goal_type": {
                "product": {"closed_tasks": 2},
                "retro": {"closed_tasks": 0},
                "meta": {"closed_tasks": 4},
            },
            "entries": {
                "fails": 1,
                "failure_reasons": {"unclear_task": 1},
            },
        }
    )

    assert "Product quality review has not started, so result-fit signals are still missing." in review
    assert "The closed product-goal sample is still small, so workflow conclusions remain provisional." in review
    assert "Meta work still outweighs product delivery, so local optimizations may not transfer cleanly to real product work." in review
    assert "Failed entries exist, especially around unclear_task." in review
    assert "Complete cost coverage is still partial across the full history, so complete covered-success averages are a strict subset view." in review


def test_next_goal_id_ignores_malformed_and_other_day_ids() -> None:
    goal_id = next_goal_id(
        [
            {"goal_id": "2026-03-29-001"},
            {"goal_id": "2026-03-29-0999"},
            {"goal_id": "2026-03-29-abc"},
            {"goal_id": "2026-03-28-999"},
            {"goal_id": None},
        ],
        now=datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
    )

    assert goal_id == "2026-03-29-002"


def test_compute_numeric_delta_returns_none_for_non_positive_change() -> None:
    assert compute_numeric_delta(5, 5) is None
    assert compute_numeric_delta(5, 4) is None
    assert compute_numeric_delta(None, 7) == 7
    assert compute_numeric_delta(5, 8) == 3


def test_parse_iso_datetime_rejects_missing_timezone() -> None:
    with pytest.raises(ValueError, match="timezone offset is required"):
        parse_iso_datetime("2026-03-29T12:00:00", "started_at")


def test_validate_goal_record_rejects_missing_required_field() -> None:
    goal = make_goal_dict()
    del goal["title"]
    with pytest.raises(ValueError, match="Missing required goal field: title"):
        validate_goal_record(goal)


def test_validate_goal_record_rejects_blank_model() -> None:
    with pytest.raises(ValueError, match="model cannot be empty"):
        validate_goal_record(
            make_goal_dict(
                model="   ",
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:05:00+00:00",
                status="success",
                attempts=1,
            )
        )


def test_validate_goal_record_rejects_non_product_result_fit() -> None:
    with pytest.raises(ValueError, match="result_fit is only allowed for product goals"):
        validate_goal_record(
            make_goal_dict(
                title="Retro with fit",
                goal_type="retro",
                status="success",
                attempts=1,
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:05:00+00:00",
                result_fit="partial_fit",
            )
        )


def test_validate_goal_record_rejects_success_with_miss_result_fit() -> None:
    with pytest.raises(ValueError, match="result_fit miss is not allowed when status is success"):
        validate_goal_record(
            make_goal_dict(
                title="Success with miss",
                status="success",
                attempts=1,
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:05:00+00:00",
                result_fit="miss",
            )
        )


def test_validate_entry_record_rejects_non_bool_inferred_flag() -> None:
    with pytest.raises(ValueError, match="Invalid type for entry field: inferred"):
        validate_entry_record(
            make_entry_dict(
                inferred="yes",
                started_at="2026-03-29T09:00:00+00:00",
            )
        )


def test_validate_metrics_data_rejects_supersession_cycle(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    data = {
        "summary": {},
        "goals": [
            make_goal_dict(
                goal_id="goal-a",
                title="Goal A",
                supersedes_goal_id="goal-b",
                status="success",
                attempts=1,
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:01:00+00:00",
            ),
            make_goal_dict(
                goal_id="goal-b",
                title="Goal B",
                supersedes_goal_id="goal-a",
                status="success",
                attempts=1,
                started_at="2026-03-29T09:02:00+00:00",
                finished_at="2026-03-29T09:03:00+00:00",
            ),
        ],
        "entries": [],
    }

    with pytest.raises(ValueError, match="Detected supersession cycle"):
        validate_metrics_data(data, metrics_path)


def test_validate_metrics_data_rejects_unknown_superseded_goal(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    with pytest.raises(ValueError, match="Referenced superseded goal not found: missing-goal"):
        validate_metrics_data(
            {
                "summary": {},
                "goals": [
                    make_goal_dict(
                        goal_id="goal-a",
                        title="Goal A",
                        supersedes_goal_id="missing-goal",
                        status="success",
                        attempts=1,
                        started_at="2026-03-29T09:00:00+00:00",
                        finished_at="2026-03-29T09:01:00+00:00",
                    )
                ],
                "entries": [],
            },
            metrics_path,
        )


def test_sync_goal_attempt_entries_creates_and_closes_attempt_history() -> None:
    data = {"entries": []}
    previous_goal = make_goal_dict(
        goal_id="goal-1",
        status="in_progress",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
        notes="First attempt started",
    )
    data["entries"] = [
        make_entry_dict(
            entry_id="goal-1-attempt-001",
            goal_id="goal-1",
            status="in_progress",
            started_at="2026-03-29T09:00:00+00:00",
            notes="First attempt started",
        )
    ]
    goal = make_goal_dict(
        goal_id="goal-1",
        status="success",
        attempts=2,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        cost_usd=0.2,
        tokens_total=500,
        notes="Second attempt succeeded",
    )

    sync_goal_attempt_entries(data, goal, previous_goal)

    entries = sorted(data["entries"], key=lambda entry: entry["entry_id"])
    assert len(entries) == 2
    assert entries[0]["status"] == "fail"
    assert entries[0]["inferred"] is True
    assert entries[0]["failure_reason"] is None
    assert entries[0]["finished_at"] == "2026-03-29T09:10:00+00:00"
    assert entries[1]["status"] == "success"
    assert entries[1]["inferred"] is False
    assert entries[1]["failure_reason"] is None
    assert entries[1]["cost_usd"] == 0.2
    assert entries[1]["tokens_total"] == 500
    assert entries[1]["model"] is None
    assert goal["model"] is None


def test_sync_goal_attempt_entries_preserves_model_on_latest_entry_and_summary() -> None:
    data = {"entries": []}
    previous_goal = make_goal_dict(
        goal_id="goal-1",
        status="in_progress",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
        model="gpt-5",
        notes="First attempt started",
    )
    data["entries"] = [
        make_entry_dict(
            entry_id="goal-1-attempt-001",
            goal_id="goal-1",
            status="in_progress",
            started_at="2026-03-29T09:00:00+00:00",
            model="gpt-5",
            notes="First attempt started",
        )
    ]
    goal = make_goal_dict(
        goal_id="goal-1",
        status="success",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        cost_usd=0.2,
        tokens_total=500,
        model="gpt-5",
        notes="Second attempt succeeded",
    )

    sync_goal_attempt_entries(data, goal, previous_goal)

    assert data["entries"][0]["model"] == "gpt-5"
    assert goal["model"] == "gpt-5"


def test_sync_goal_attempt_entries_clears_goal_model_for_mixed_attempts() -> None:
    data = {"entries": []}
    previous_goal = make_goal_dict(
        goal_id="goal-1",
        status="in_progress",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
        model="gpt-5",
    )
    data["entries"] = [
        make_entry_dict(
            entry_id="goal-1-attempt-001",
            goal_id="goal-1",
            status="success",
            started_at="2026-03-29T09:00:00+00:00",
            finished_at="2026-03-29T09:05:00+00:00",
            cost_usd=0.1,
            tokens_total=200,
            model="gpt-5",
        )
    ]
    goal = make_goal_dict(
        goal_id="goal-1",
        status="success",
        attempts=2,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        cost_usd=0.3,
        tokens_total=700,
        model="gpt-5.4",
    )

    sync_goal_attempt_entries(data, goal, previous_goal)

    entries = sorted(data["entries"], key=lambda entry: entry["entry_id"])
    assert entries[0]["model"] == "gpt-5"
    assert entries[1]["model"] == "gpt-5.4"
    assert goal["model"] is None


def test_sync_goal_attempt_entries_trims_excess_entries_when_attempts_drop() -> None:
    data = {
        "entries": [
            make_entry_dict(
                entry_id="goal-1-attempt-001",
                goal_id="goal-1",
                status="fail",
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:01:00+00:00",
                failure_reason="validation_failed",
                notes="Attempt one",
            ),
            make_entry_dict(
                entry_id="goal-1-attempt-002",
                goal_id="goal-1",
                status="success",
                started_at="2026-03-29T09:02:00+00:00",
                finished_at="2026-03-29T09:03:00+00:00",
                cost_usd=0.1,
                tokens_total=200,
                notes="Attempt two",
            ),
        ]
    }
    goal = make_goal_dict(
        goal_id="goal-1",
        status="success",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:03:00+00:00",
        cost_usd=0.1,
        tokens_total=200,
        notes="Compressed history",
    )

    sync_goal_attempt_entries(data, goal, None)

    assert [entry["entry_id"] for entry in data["entries"]] == ["goal-1-attempt-001"]


def test_apply_attempt_usage_deltas_uses_initial_goal_values_without_previous_goal() -> None:
    latest_entry = {"cost_usd": None, "tokens_total": None}

    apply_attempt_usage_deltas(
        latest_entry,
        {"cost_usd": 0.25, "tokens_total": 123},
        None,
    )

    assert latest_entry["cost_usd"] == 0.25
    assert latest_entry["tokens_total"] == 123


def test_update_latest_attempt_entry_returns_none_for_empty_entries() -> None:
    assert update_latest_attempt_entry([], {"goal_type": "product", "status": "success"}) is None


def test_ensure_goal_type_update_allowed_rejects_existing_attempt_history() -> None:
    goal = make_goal_record(
        goal_id="goal-1",
        title="Goal one",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
    )

    with pytest.raises(ValueError, match="goal_id already exists as a product goal"):
        ensure_goal_type_update_allowed(
            [{"entry_id": "goal-1-attempt-001", "goal_id": "goal-1"}],
            goal,
            "meta",
        )


def test_create_goal_record_rejects_linked_goal_type_mismatch() -> None:
    tasks = [
        make_goal_dict(
            goal_id="goal-1",
            title="Retro goal",
            goal_type="retro",
            status="success",
            attempts=1,
            started_at="2026-03-29T09:00:00+00:00",
            finished_at="2026-03-29T09:01:00+00:00",
        )
    ]

    with pytest.raises(ValueError, match="linked tasks must use the same task_type"):
        create_goal_record(
            tasks=tasks,
            task_id="goal-2",
            title="Product follow-up",
            task_type="product",
            linked_task_id="goal-1",
            started_at="2026-03-29T09:02:00+00:00",
        )


def test_apply_goal_updates_rejects_blank_title() -> None:
    task = make_goal_record(
        goal_id="goal-1",
        title="Original",
        started_at="2026-03-29T09:00:00+00:00",
    )

    with pytest.raises(ValueError, match="title cannot be empty"):
        apply_goal_updates(
            entries=[],
            task=task,
            title="   ",
            task_type=None,
            status=None,
            attempts_delta=None,
            attempts_abs=None,
            cost_usd_add=None,
            cost_usd_set=None,
            input_tokens_add=None,
            cached_input_tokens_add=None,
            output_tokens_add=None,
            tokens_add=None,
            tokens_set=None,
            usage_cost_usd=None,
            usage_input_tokens=None,
            usage_cached_input_tokens=None,
            usage_output_tokens=None,
            usage_total_tokens=None,
            auto_cost_usd=None,
            auto_input_tokens=None,
            auto_cached_input_tokens=None,
            auto_output_tokens=None,
            auto_total_tokens=None,
            model=None,
            usage_model=None,
            auto_model=None,
            failure_reason=None,
            notes=None,
            started_at=None,
            finished_at=None,
        )


def test_finalize_goal_update_sets_attempts_and_clears_failure_reason_on_success() -> None:
    task = make_goal_record(
        goal_id="goal-1",
        title="Ship change",
        status="success",
        started_at="2026-03-29T09:00:00+00:00",
        failure_reason="validation_failed",
    )

    finalize_goal_update(task)

    assert task.attempts == 1
    assert task.failure_reason is None
    assert task.finished_at is not None


def test_parse_usage_event_extracts_expected_fields() -> None:
    event = MODULE.parse_usage_event(
        'event.name="codex.sse_event" '
        "event.kind=response.completed "
        "input_token_count=1000 "
        "output_token_count=500 "
        "cached_token_count=100 "
        "reasoning_token_count=25 "
        "tool_token_count=10 "
        "event.timestamp=2026-03-29T09:05:00.000Z "
        "conversation.id=thread-123 "
        "model=gpt-5.4 "
        "slug=gpt-5.4"
    )

    assert event is not None
    assert event["model"] == "gpt-5.4"
    assert event["input_tokens"] == 1000
    assert event["cached_input_tokens"] == 100
    assert event["output_tokens"] == 500
    assert event["reasoning_tokens"] == 25
    assert event["tool_tokens"] == 10


def test_resolve_pricing_model_alias_accepts_current_model_suffixes() -> None:
    pricing = {
        "gpt-5": {
            "input_per_million_usd": 1.25,
            "cached_input_per_million_usd": 0.125,
            "output_per_million_usd": 10.0,
        },
        "gpt-5-mini": {
            "input_per_million_usd": 0.25,
            "cached_input_per_million_usd": 0.025,
            "output_per_million_usd": 2.0,
        },
    }

    assert MODULE.resolve_pricing_model_alias("gpt-5.4", pricing) == "gpt-5"
    assert MODULE.resolve_pricing_model_alias("gpt-5.4-mini", pricing) == "gpt-5-mini"


def test_resolve_codex_usage_window_returns_none_without_matching_thread(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    pricing_path = tmp_path / "pricing.json"

    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO threads (id, cwd, updated_at) VALUES (?, ?, ?)",
            ("thread-123", str(tmp_path / "other"), 1),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_log_body TEXT
            )
            """
        )

    assert MODULE.resolve_codex_usage_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=tmp_path,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=pricing_path,
    ) == (None, None, None, None, None, None)


def test_resolve_codex_usage_window_falls_back_to_session_token_counts(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    pricing_path = tmp_path / "pricing.json"
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "29"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / "rollout-2026-03-29T11-27-52-thread-123.jsonl"

    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-29T09:05:00.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 1000,
                                    "cached_input_tokens": 100,
                                    "output_tokens": 500,
                                    "reasoning_output_tokens": 25,
                                    "total_tokens": 1625,
                                }
                            },
                        },
                    }
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO threads (id, cwd, updated_at) VALUES (?, ?, ?)",
            ("thread-123", str(tmp_path), 1),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_log_body TEXT,
                thread_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                "session_loop thread.id=thread-123 model=gpt-5.4 response.completed",
                "thread-123",
            ),
        )

    assert MODULE.resolve_codex_usage_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=tmp_path,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=pricing_path,
    ) == (0.006263, 1625, 1000, 100, 500, "gpt-5.4")


def test_resolve_codex_usage_window_sums_multiple_session_token_events(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    pricing_path = tmp_path / "pricing.json"
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "29"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / "rollout-2026-03-29T11-27-52-thread-123.jsonl"

    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-29T09:05:00.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 1000,
                                    "cached_input_tokens": 100,
                                    "output_tokens": 500,
                                    "reasoning_output_tokens": 25,
                                    "total_tokens": 1625,
                                }
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-29T09:06:00.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 2000,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 250,
                                    "reasoning_output_tokens": 10,
                                    "total_tokens": 2260,
                                }
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO threads (id, cwd, updated_at) VALUES (?, ?, ?)",
            ("thread-123", str(tmp_path), 1),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_log_body TEXT,
                thread_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                "session_loop thread.id=thread-123 model=gpt-5.4 response.completed",
                "thread-123",
            ),
        )

    assert MODULE.resolve_codex_usage_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=tmp_path,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=pricing_path,
    ) == (0.011263, 3885, 3000, 100, 750, "gpt-5.4")


def test_resolve_codex_usage_window_ignores_session_events_outside_window(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    pricing_path = tmp_path / "pricing.json"
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "29"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / "rollout-2026-03-29T11-27-52-thread-123.jsonl"

    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-29T08:59:59.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 9999,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 1,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 10000,
                                }
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-29T09:05:00.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 1000,
                                    "cached_input_tokens": 100,
                                    "output_tokens": 500,
                                    "reasoning_output_tokens": 25,
                                    "total_tokens": 1625,
                                }
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-29T09:10:01.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 9999,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 1,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 10000,
                                }
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO threads (id, cwd, updated_at) VALUES (?, ?, ?)",
            ("thread-123", str(tmp_path), 1),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_log_body TEXT,
                thread_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                "session_loop thread.id=thread-123 model=gpt-5.4 response.completed",
                "thread-123",
            ),
        )

    assert MODULE.resolve_codex_usage_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=tmp_path,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=pricing_path,
    ) == (0.006263, 1625, 1000, 100, 500, "gpt-5.4")


def test_resolve_codex_usage_window_recovers_tokens_without_cost_when_model_missing(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    pricing_path = tmp_path / "pricing.json"
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "29"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / "rollout-2026-03-29T11-27-52-thread-123.jsonl"

    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rollout_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-03-29T09:05:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 100,
                            "output_tokens": 500,
                            "reasoning_output_tokens": 25,
                            "total_tokens": 1625,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO threads (id, cwd, updated_at) VALUES (?, ?, ?)",
            ("thread-123", str(tmp_path), 1),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_log_body TEXT,
                thread_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                "session_loop thread.id=thread-123 response.completed",
                "thread-123",
            ),
        )

    assert MODULE.resolve_codex_usage_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=tmp_path,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=pricing_path,
    ) == (None, 1625, 1000, 100, 500, None)


def test_resolve_codex_usage_window_prefers_legacy_sse_events_over_session_fallback(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    pricing_path = tmp_path / "pricing.json"
    sessions_dir = tmp_path / "sessions" / "2026" / "03" / "29"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / "rollout-2026-03-29T11-27-52-thread-123.jsonl"

    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rollout_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-03-29T09:05:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 9999,
                            "cached_input_tokens": 0,
                            "output_tokens": 1,
                            "reasoning_output_tokens": 0,
                            "total_tokens": 10000,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO threads (id, cwd, updated_at) VALUES (?, ?, ?)",
            ("thread-123", str(tmp_path), 1),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_log_body TEXT,
                thread_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                'event.name="codex.sse_event" event.kind=response.completed '
                "input_token_count=1000 output_token_count=500 cached_token_count=100 "
                "reasoning_token_count=0 tool_token_count=0 "
                "event.timestamp=2026-03-29T09:05:00.000Z conversation.id=thread-123 "
                "model=gpt-5.4 slug=gpt-5.4",
                "thread-123",
            ),
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                "session_loop thread.id=thread-123 model=gpt-5.4 response.completed",
                "thread-123",
            ),
        )

    assert MODULE.resolve_codex_usage_window(
        state_path=state_path,
        logs_path=logs_path,
        cwd=tmp_path,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=pricing_path,
    ) == (0.006263, 1600, 1000, 100, 500, "gpt-5.4")


def test_load_pricing_rejects_negative_values(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": -1.0,
                        "cached_input_per_million_usd": 0.125,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Pricing value cannot be negative"):
        MODULE.load_pricing(pricing_path)


def test_load_pricing_requires_all_fields(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "models": {
                    "gpt-5": {
                        "input_per_million_usd": 1.25,
                        "output_per_million_usd": 10.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing pricing field"):
        MODULE.load_pricing(pricing_path)


def test_resolve_usage_costs_requires_token_fields_when_model_is_given() -> None:
    with pytest.raises(ValueError, match="At least one usage token field is required"):
        MODULE.resolve_usage_costs(
            pricing_path=SCRIPT_PATH.parents[1] / "pricing" / "model_pricing.json",
            model="gpt-5",
            input_tokens=None,
            cached_input_tokens=None,
            output_tokens=None,
            explicit_cost_fields_used=False,
            explicit_token_fields_used=False,
        )
