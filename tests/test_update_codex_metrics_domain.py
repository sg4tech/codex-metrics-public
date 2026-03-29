from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_codex_metrics.py"
SPEC = importlib.util.spec_from_file_location("update_codex_metrics_module", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_compute_summary_block_uses_closed_goals_for_attempt_average() -> None:
    summary = MODULE.compute_summary_block(
        [
            MODULE.EffectiveGoalRecord(
                goal_id="goal-1",
                title="Goal one",
                goal_type="product",
                status="success",
                attempts=2,
                started_at=None,
                finished_at=None,
                cost_usd=0.5,
                cost_usd_known=0.5,
                cost_complete=True,
                tokens_total=500,
                tokens_total_known=500,
                tokens_complete=True,
                failure_reason=None,
                notes=None,
                supersedes_goal_id=None,
            ),
            MODULE.EffectiveGoalRecord(
                goal_id="goal-2",
                title="Goal two",
                goal_type="product",
                status="fail",
                attempts=4,
                started_at=None,
                finished_at=None,
                cost_usd=None,
                cost_usd_known=None,
                cost_complete=False,
                tokens_total=None,
                tokens_total_known=None,
                tokens_complete=False,
                failure_reason="other",
                notes=None,
                supersedes_goal_id=None,
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
    summary = MODULE.compute_summary_block(
        [
            MODULE.EffectiveGoalRecord(
                goal_id="goal-1",
                title="Goal one",
                goal_type="product",
                status="success",
                attempts=1,
                started_at=None,
                finished_at=None,
                cost_usd=0.5,
                cost_usd_known=0.5,
                cost_complete=True,
                tokens_total=500,
                tokens_total_known=500,
                tokens_complete=True,
                failure_reason=None,
                notes=None,
                supersedes_goal_id=None,
            ),
            MODULE.EffectiveGoalRecord(
                goal_id="goal-2",
                title="Goal two",
                goal_type="product",
                status="success",
                attempts=2,
                started_at=None,
                finished_at=None,
                cost_usd=None,
                cost_usd_known=1.0,
                cost_complete=False,
                tokens_total=None,
                tokens_total_known=1200,
                tokens_complete=False,
                failure_reason=None,
                notes=None,
                supersedes_goal_id=None,
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


def test_build_effective_goals_merges_superseded_chain_attempts_and_known_cost() -> None:
    effective_goals = MODULE.build_effective_goals(
        [
            MODULE.GoalRecord(
                goal_id="goal-1",
                title="Original goal",
                goal_type="product",
                supersedes_goal_id=None,
                status="fail",
                attempts=1,
                started_at="2026-03-29T09:00:00+00:00",
                finished_at="2026-03-29T09:05:00+00:00",
                cost_usd=None,
                tokens_total=None,
                failure_reason="validation_failed",
                notes="First attempt failed",
            ),
            MODULE.GoalRecord(
                goal_id="goal-2",
                title="Replacement goal",
                goal_type="product",
                supersedes_goal_id="goal-1",
                status="success",
                attempts=2,
                started_at="2026-03-29T09:06:00+00:00",
                finished_at="2026-03-29T09:10:00+00:00",
                cost_usd=0.25,
                tokens_total=1000,
                failure_reason=None,
                notes="Second chain succeeded",
            ),
        ]
    )

    assert len(effective_goals) == 1
    goal = effective_goals[0]
    assert goal.goal_id == "goal-2"
    assert goal.status == "success"
    assert goal.attempts == 3
    assert goal.started_at == "2026-03-29T09:00:00+00:00"
    assert goal.finished_at == "2026-03-29T09:10:00+00:00"
    assert goal.cost_usd_known == 0.25
    assert goal.cost_usd is None
    assert goal.tokens_total_known == 1000
    assert goal.tokens_total is None


def test_compute_entry_summary_counts_failure_reasons_from_failed_entries_only() -> None:
    summary = MODULE.compute_entry_summary(
        [
            MODULE.AttemptEntryRecord(
                entry_id="entry-1",
                goal_id="goal-1",
                entry_type="product",
                inferred=False,
                status="success",
                started_at=None,
                finished_at=None,
                cost_usd=0.2,
                tokens_total=300,
                failure_reason=None,
                notes=None,
            ),
            MODULE.AttemptEntryRecord(
                entry_id="entry-2",
                goal_id="goal-1",
                entry_type="product",
                inferred=False,
                status="fail",
                started_at=None,
                finished_at=None,
                cost_usd=None,
                tokens_total=None,
                failure_reason="unclear_task",
                notes=None,
            ),
            MODULE.AttemptEntryRecord(
                entry_id="entry-3",
                goal_id="goal-2",
                entry_type="product",
                inferred=True,
                status="fail",
                started_at=None,
                finished_at=None,
                cost_usd=None,
                tokens_total=None,
                failure_reason=None,
                notes=None,
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


def test_build_operator_review_surfaces_retry_and_cost_visibility() -> None:
    review = MODULE.build_operator_review(
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

    assert "Product sample is still small; treat workflow conclusions as provisional." in review
    assert "Meta work still outweighs product delivery; validate changes on real product goals." in review
    assert "Retry pressure exists; inspect failed entries, especially unclear_task." in review
    assert "Cost visibility is partial; use known-cost metrics as directional, not final." in review
    assert "Full cost coverage is still partial; treat complete covered-success averages as strict subset signals." in review


def test_next_goal_id_ignores_malformed_and_other_day_ids() -> None:
    goal_id = MODULE.next_goal_id(
        [
            {"goal_id": "2026-03-29-001"},
            {"goal_id": "2026-03-29-0999"},
            {"goal_id": "2026-03-29-abc"},
            {"goal_id": "2026-03-28-999"},
            {"goal_id": None},
        ],
        now=MODULE.datetime(2026, 3, 29, 12, 0, tzinfo=MODULE.timezone.utc),
    )

    assert goal_id == "2026-03-29-002"


def test_compute_numeric_delta_returns_none_for_non_positive_change() -> None:
    assert MODULE.compute_numeric_delta(5, 5) is None
    assert MODULE.compute_numeric_delta(5, 4) is None
    assert MODULE.compute_numeric_delta(None, 7) == 7
    assert MODULE.compute_numeric_delta(5, 8) == 3


def test_parse_iso_datetime_rejects_missing_timezone() -> None:
    with pytest.raises(ValueError, match="timezone offset is required"):
        MODULE.parse_iso_datetime("2026-03-29T12:00:00", "started_at")


def test_validate_goal_record_rejects_missing_required_field() -> None:
    with pytest.raises(ValueError, match="Missing required goal field: title"):
        MODULE.validate_goal_record(
            {
                "goal_id": "goal-1",
                "goal_type": "product",
                "supersedes_goal_id": None,
                "status": "in_progress",
                "attempts": 0,
                "started_at": None,
                "finished_at": None,
                "cost_usd": None,
                "tokens_total": None,
                "failure_reason": None,
                "notes": None,
            }
        )


def test_validate_goal_record_rejects_non_product_result_fit() -> None:
    with pytest.raises(ValueError, match="result_fit is only allowed for product goals"):
        MODULE.validate_goal_record(
            {
                "goal_id": "goal-1",
                "title": "Retro with fit",
                "goal_type": "retro",
                "supersedes_goal_id": None,
                "status": "success",
                "attempts": 1,
                "started_at": "2026-03-29T09:00:00+00:00",
                "finished_at": "2026-03-29T09:05:00+00:00",
                "cost_usd": None,
                "tokens_total": None,
                "failure_reason": None,
                "notes": None,
                "result_fit": "partial_fit",
            }
        )


def test_validate_goal_record_rejects_success_with_miss_result_fit() -> None:
    with pytest.raises(ValueError, match="result_fit miss is not allowed when status is success"):
        MODULE.validate_goal_record(
            {
                "goal_id": "goal-1",
                "title": "Success with miss",
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
                "result_fit": "miss",
            }
        )


def test_validate_entry_record_rejects_non_bool_inferred_flag() -> None:
    with pytest.raises(ValueError, match="Invalid type for entry field: inferred"):
        MODULE.validate_entry_record(
            {
                "entry_id": "goal-1-attempt-001",
                "goal_id": "goal-1",
                "entry_type": "product",
                "inferred": "yes",
                "status": "in_progress",
                "started_at": "2026-03-29T09:00:00+00:00",
                "finished_at": None,
                "cost_usd": None,
                "tokens_total": None,
                "failure_reason": None,
                "notes": None,
            }
        )


def test_validate_metrics_data_rejects_supersession_cycle(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    data = {
        "summary": {},
        "goals": [
            {
                "goal_id": "goal-a",
                "title": "Goal A",
                "goal_type": "product",
                "supersedes_goal_id": "goal-b",
                "status": "success",
                "attempts": 1,
                "started_at": "2026-03-29T09:00:00+00:00",
                "finished_at": "2026-03-29T09:01:00+00:00",
                "cost_usd": None,
                "tokens_total": None,
                "failure_reason": None,
                "notes": None,
            },
            {
                "goal_id": "goal-b",
                "title": "Goal B",
                "goal_type": "product",
                "supersedes_goal_id": "goal-a",
                "status": "success",
                "attempts": 1,
                "started_at": "2026-03-29T09:02:00+00:00",
                "finished_at": "2026-03-29T09:03:00+00:00",
                "cost_usd": None,
                "tokens_total": None,
                "failure_reason": None,
                "notes": None,
            },
        ],
        "entries": [],
    }

    with pytest.raises(ValueError, match="Detected supersession cycle"):
        MODULE.validate_metrics_data(data, metrics_path)


def test_validate_metrics_data_rejects_unknown_superseded_goal(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    with pytest.raises(ValueError, match="Referenced superseded goal not found: missing-goal"):
        MODULE.validate_metrics_data(
            {
                "summary": {},
                "goals": [
                    {
                        "goal_id": "goal-a",
                        "title": "Goal A",
                        "goal_type": "product",
                        "supersedes_goal_id": "missing-goal",
                        "status": "success",
                        "attempts": 1,
                        "started_at": "2026-03-29T09:00:00+00:00",
                        "finished_at": "2026-03-29T09:01:00+00:00",
                        "cost_usd": None,
                        "tokens_total": None,
                        "failure_reason": None,
                        "notes": None,
                    }
                ],
                "entries": [],
            },
            metrics_path,
        )


def test_sync_goal_attempt_entries_creates_and_closes_attempt_history() -> None:
    data = {"entries": []}
    previous_goal = {
        "goal_id": "goal-1",
        "goal_type": "product",
        "status": "in_progress",
        "attempts": 1,
        "started_at": "2026-03-29T09:00:00+00:00",
        "finished_at": None,
        "cost_usd": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": "First attempt started",
    }
    data["entries"] = [
        {
            "entry_id": "goal-1-attempt-001",
            "goal_id": "goal-1",
            "entry_type": "product",
            "inferred": False,
            "status": "in_progress",
            "started_at": "2026-03-29T09:00:00+00:00",
            "finished_at": None,
            "cost_usd": None,
            "tokens_total": None,
            "failure_reason": None,
            "notes": "First attempt started",
        }
    ]
    goal = {
        "goal_id": "goal-1",
        "goal_type": "product",
        "status": "success",
        "attempts": 2,
        "started_at": "2026-03-29T09:00:00+00:00",
        "finished_at": "2026-03-29T09:10:00+00:00",
        "cost_usd": 0.2,
        "tokens_total": 500,
        "failure_reason": None,
        "notes": "Second attempt succeeded",
    }

    MODULE.sync_goal_attempt_entries(data, goal, previous_goal)

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


def test_sync_goal_attempt_entries_trims_excess_entries_when_attempts_drop() -> None:
    data = {
        "entries": [
            {
                "entry_id": "goal-1-attempt-001",
                "goal_id": "goal-1",
                "entry_type": "product",
                "inferred": False,
                "status": "fail",
                "started_at": "2026-03-29T09:00:00+00:00",
                "finished_at": "2026-03-29T09:01:00+00:00",
                "cost_usd": None,
                "tokens_total": None,
                "failure_reason": "validation_failed",
                "notes": "Attempt one",
            },
            {
                "entry_id": "goal-1-attempt-002",
                "goal_id": "goal-1",
                "entry_type": "product",
                "inferred": False,
                "status": "success",
                "started_at": "2026-03-29T09:02:00+00:00",
                "finished_at": "2026-03-29T09:03:00+00:00",
                "cost_usd": 0.1,
                "tokens_total": 200,
                "failure_reason": None,
                "notes": "Attempt two",
            },
        ]
    }
    goal = {
        "goal_id": "goal-1",
        "goal_type": "product",
        "status": "success",
        "attempts": 1,
        "started_at": "2026-03-29T09:00:00+00:00",
        "finished_at": "2026-03-29T09:03:00+00:00",
        "cost_usd": 0.1,
        "tokens_total": 200,
        "failure_reason": None,
        "notes": "Compressed history",
    }

    MODULE.sync_goal_attempt_entries(data, goal, None)

    assert [entry["entry_id"] for entry in data["entries"]] == ["goal-1-attempt-001"]


def test_apply_attempt_usage_deltas_uses_initial_goal_values_without_previous_goal() -> None:
    latest_entry = {"cost_usd": None, "tokens_total": None}

    MODULE.apply_attempt_usage_deltas(
        latest_entry,
        {"cost_usd": 0.25, "tokens_total": 123},
        None,
    )

    assert latest_entry["cost_usd"] == 0.25
    assert latest_entry["tokens_total"] == 123


def test_update_latest_attempt_entry_returns_none_for_empty_entries() -> None:
    assert MODULE.update_latest_attempt_entry([], {"goal_type": "product", "status": "success"}) is None


def test_ensure_goal_type_update_allowed_rejects_existing_attempt_history() -> None:
    goal = MODULE.GoalRecord(
        goal_id="goal-1",
        title="Goal one",
        goal_type="product",
        supersedes_goal_id=None,
        status="in_progress",
        attempts=1,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at=None,
        cost_usd=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
    )

    with pytest.raises(ValueError, match="goal_id already exists as a product goal"):
        MODULE.ensure_goal_type_update_allowed(
            [{"entry_id": "goal-1-attempt-001", "goal_id": "goal-1"}],
            goal,
            "meta",
        )


def test_create_goal_record_rejects_linked_goal_type_mismatch() -> None:
    tasks = [
        {
            "goal_id": "goal-1",
            "title": "Retro goal",
            "goal_type": "retro",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-29T09:00:00+00:00",
            "finished_at": "2026-03-29T09:01:00+00:00",
            "cost_usd": None,
            "tokens_total": None,
            "failure_reason": None,
            "notes": None,
        }
    ]

    with pytest.raises(ValueError, match="linked tasks must use the same task_type"):
        MODULE.create_goal_record(
            tasks=tasks,
            task_id="goal-2",
            title="Product follow-up",
            task_type="product",
            linked_task_id="goal-1",
            started_at="2026-03-29T09:02:00+00:00",
        )


def test_apply_goal_updates_rejects_blank_title() -> None:
    task = MODULE.GoalRecord(
        goal_id="goal-1",
        title="Original",
        goal_type="product",
        supersedes_goal_id=None,
        status="in_progress",
        attempts=0,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at=None,
        cost_usd=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
    )

    with pytest.raises(ValueError, match="title cannot be empty"):
        MODULE.apply_goal_updates(
            entries=[],
            task=task,
            title="   ",
            task_type=None,
            status=None,
            attempts_delta=None,
            attempts_abs=None,
            cost_usd_add=None,
            cost_usd_set=None,
            tokens_add=None,
            tokens_set=None,
            usage_cost_usd=None,
            usage_total_tokens=None,
            auto_cost_usd=None,
            auto_total_tokens=None,
            failure_reason=None,
            notes=None,
            started_at=None,
            finished_at=None,
        )


def test_finalize_goal_update_sets_attempts_and_clears_failure_reason_on_success() -> None:
    task = MODULE.GoalRecord(
        goal_id="goal-1",
        title="Ship change",
        goal_type="product",
        supersedes_goal_id=None,
        status="success",
        attempts=0,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at=None,
        cost_usd=None,
        tokens_total=None,
        failure_reason="validation_failed",
        notes=None,
    )

    MODULE.finalize_goal_update(task)

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
    ) == (None, None)


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
    ) == (0.006263, 1625)


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
    ) == (0.011263, 3885)


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
    ) == (0.006263, 1625)


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
    ) == (None, 1625)


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
    ) == (0.006263, 1600)


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
