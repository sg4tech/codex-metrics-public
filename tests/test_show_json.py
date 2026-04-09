from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from ai_agents_metrics import commands
from ai_agents_metrics.reporting import render_summary_json


class _FakeDecision:
    action = "warning"
    message = "working tree has meaningful changes"


class _FakeResolution:
    decision = _FakeDecision()


class _FakeRuntime:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def load_metrics(self, path: Path) -> dict[str, object]:
        assert path == Path("/metrics.json")
        return self.data

    def recompute_summary(self, data: dict[str, object]) -> None:
        assert data is self.data

    def resolve_workflow_resolution(self, data: dict[str, object], cwd: Path, event: object) -> _FakeResolution:
        assert data is self.data
        assert cwd == Path.cwd()
        return _FakeResolution()

    def print_summary(self, data: dict[str, object]) -> None:
        raise AssertionError("print_summary should not be called in JSON mode")

    def render_summary_json(self, data: dict[str, object]) -> str:
        return render_summary_json(data)


def test_render_summary_json_includes_product_quality_and_recommendations() -> None:
    data = {
        "summary": {
            "closed_tasks": 1,
            "successes": 1,
            "fails": 0,
            "total_attempts": 1,
            "total_cost_usd": 1.0,
            "total_input_tokens": 10,
            "total_cached_input_tokens": 0,
            "total_output_tokens": 20,
            "total_tokens": 30,
            "success_rate": 1.0,
            "attempts_per_closed_task": 1.0,
            "known_cost_successes": 1,
            "known_token_successes": 1,
            "known_token_breakdown_successes": 1,
            "complete_cost_successes": 1,
            "complete_token_successes": 1,
            "complete_token_breakdown_successes": 1,
            "model_summary_goals": 1,
            "model_complete_goals": 1,
            "mixed_model_goals": 0,
            "known_cost_per_success_usd": 1.0,
            "known_cost_per_success_tokens": 30.0,
            "complete_cost_per_covered_success_usd": 1.0,
            "complete_cost_per_covered_success_tokens": 30.0,
            "by_goal_type": {
                "product": {
                    "closed_tasks": 1,
                    "successes": 1,
                    "fails": 0,
                    "total_attempts": 1,
                    "total_cost_usd": 1.0,
                    "total_input_tokens": 10,
                    "total_cached_input_tokens": 0,
                    "total_output_tokens": 20,
                    "total_tokens": 30,
                    "success_rate": 1.0,
                    "attempts_per_closed_task": 1.0,
                    "known_cost_successes": 1,
                    "known_token_successes": 1,
                    "known_token_breakdown_successes": 1,
                    "complete_cost_successes": 1,
                    "complete_token_successes": 1,
                    "complete_token_breakdown_successes": 1,
                    "known_cost_per_success_usd": 1.0,
                    "known_cost_per_success_tokens": 30.0,
                    "complete_cost_per_covered_success_usd": 1.0,
                    "complete_cost_per_covered_success_tokens": 30.0,
                },
                "retro": {"closed_tasks": 0},
                "meta": {"closed_tasks": 0},
            },
            "entries": {
                "closed_entries": 1,
                "successes": 1,
                "fails": 0,
                "success_rate": 1.0,
                "total_cost_usd": 1.0,
                "total_input_tokens": 10,
                "total_cached_input_tokens": 0,
                "total_output_tokens": 20,
                "total_tokens": 30,
                "failure_reasons": {},
            },
        },
        "goals": [
            {
                "goal_id": "goal-1",
                "title": "Exact fit goal",
                "goal_type": "product",
                "supersedes_goal_id": None,
                "status": "success",
                "attempts": 1,
                "started_at": "2026-04-04T10:00:00+00:00",
                "finished_at": "2026-04-04T10:05:00+00:00",
                "cost_usd": 1.0,
                "tokens_total": 30,
                "failure_reason": None,
                "notes": None,
                "result_fit": "exact_fit",
            }
        ],
        "entries": [
            {
                "entry_id": "entry-1",
                "goal_id": "goal-1",
                "entry_type": "attempt",
                "inferred": False,
                "status": "success",
                "started_at": "2026-04-04T10:00:00+00:00",
                "finished_at": "2026-04-04T10:05:00+00:00",
                "cost_usd": 1.0,
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 20,
                "tokens_total": 30,
                "failure_reason": None,
                "notes": None,
            }
        ],
    }

    payload = json.loads(render_summary_json(data))
    assert payload["product_quality"]["closed_product_goals"] == 1
    assert payload["recommendations"]


def test_handle_show_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    data = {
        "summary": {
            "closed_tasks": 1,
            "successes": 1,
            "fails": 0,
            "total_attempts": 1,
            "total_cost_usd": 1.0,
            "total_input_tokens": 10,
            "total_cached_input_tokens": 0,
            "total_output_tokens": 20,
            "total_tokens": 30,
            "success_rate": 1.0,
            "attempts_per_closed_task": 1.0,
            "known_cost_successes": 1,
            "known_token_successes": 1,
            "known_token_breakdown_successes": 1,
            "complete_cost_successes": 1,
            "complete_token_successes": 1,
            "complete_token_breakdown_successes": 1,
            "model_summary_goals": 1,
            "model_complete_goals": 1,
            "mixed_model_goals": 0,
            "known_cost_per_success_usd": 1.0,
            "known_cost_per_success_tokens": 30.0,
            "complete_cost_per_covered_success_usd": 1.0,
            "complete_cost_per_covered_success_tokens": 30.0,
            "by_goal_type": {
                "product": {
                    "closed_tasks": 1,
                    "successes": 1,
                    "fails": 0,
                    "total_attempts": 1,
                    "total_cost_usd": 1.0,
                    "total_input_tokens": 10,
                    "total_cached_input_tokens": 0,
                    "total_output_tokens": 20,
                    "total_tokens": 30,
                    "success_rate": 1.0,
                    "attempts_per_closed_task": 1.0,
                    "known_cost_successes": 1,
                    "known_token_successes": 1,
                    "known_token_breakdown_successes": 1,
                    "complete_cost_successes": 1,
                    "complete_token_successes": 1,
                    "complete_token_breakdown_successes": 1,
                    "known_cost_per_success_usd": 1.0,
                    "known_cost_per_success_tokens": 30.0,
                    "complete_cost_per_covered_success_usd": 1.0,
                    "complete_cost_per_covered_success_tokens": 30.0,
                },
                "retro": {"closed_tasks": 0},
                "meta": {"closed_tasks": 0},
            },
            "entries": {
                "closed_entries": 1,
                "successes": 1,
                "fails": 0,
                "success_rate": 1.0,
                "total_cost_usd": 1.0,
                "total_input_tokens": 10,
                "total_cached_input_tokens": 0,
                "total_output_tokens": 20,
                "total_tokens": 30,
                "failure_reasons": {},
            },
        },
        "goals": [
            {
                "goal_id": "goal-1",
                "title": "Exact fit goal",
                "goal_type": "product",
                "supersedes_goal_id": None,
                "status": "success",
                "attempts": 1,
                "started_at": "2026-04-04T10:00:00+00:00",
                "finished_at": "2026-04-04T10:05:00+00:00",
                "cost_usd": 1.0,
                "tokens_total": 30,
                "failure_reason": None,
                "notes": None,
                "result_fit": "exact_fit",
            }
        ],
        "entries": [
            {
                "entry_id": "entry-1",
                "goal_id": "goal-1",
                "entry_type": "attempt",
                "inferred": False,
                "status": "success",
                "started_at": "2026-04-04T10:00:00+00:00",
                "finished_at": "2026-04-04T10:05:00+00:00",
                "cost_usd": 1.0,
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 20,
                "tokens_total": 30,
                "failure_reason": None,
                "notes": None,
            }
        ],
    }
    runtime = _FakeRuntime(data)

    exit_code = commands.handle_show(Namespace(metrics_path="/metrics.json", json=True), runtime)

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out[captured.out.index("{"):])
    assert payload["product_quality"]["closed_product_goals"] == 1
