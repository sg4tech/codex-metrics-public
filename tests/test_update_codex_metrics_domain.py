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
    assert summary["cost_per_success_usd"] == 0.5
    assert summary["cost_per_success_tokens"] == 500.0


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
