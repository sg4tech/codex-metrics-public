from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_metrics.cost_audit import audit_cost_coverage, render_cost_audit_report


def test_cost_audit_flags_incomplete_goal_window(tmp_path: Path) -> None:
    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Closed without timestamps",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 1,
                    "started_at": None,
                    "finished_at": "2026-03-29T09:05:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                }
            ]
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=tmp_path / "state.sqlite",
        codex_logs_path=tmp_path / "logs.sqlite",
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: "ignored",
        resolve_usage_window=lambda *_args: (1.0, 10),
    )

    assert len(report.candidates) == 1
    assert report.candidates[0].category == "incomplete_goal_window"


def test_cost_audit_flags_zero_duration_goal_window(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Zero-duration window",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:00:00+00:00",
                    "cost_usd": None,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                }
            ]
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=state_path,
        codex_logs_path=logs_path,
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: "thread-1",
        resolve_usage_window=lambda *_args: (None, None),
    )

    assert len(report.candidates) == 1
    assert report.candidates[0].category == "incomplete_goal_window"
    assert "zero-duration" in report.candidates[0].reason


def test_cost_audit_flags_missing_telemetry_files(tmp_path: Path) -> None:
    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "No telemetry",
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
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=tmp_path / "state.sqlite",
        codex_logs_path=tmp_path / "logs.sqlite",
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: "ignored",
        resolve_usage_window=lambda *_args: (1.0, 10),
    )

    assert report.candidates[0].category == "telemetry_unavailable"


def test_cost_audit_flags_thread_unresolved(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "No thread",
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
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=state_path,
        codex_logs_path=logs_path,
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: None,
        resolve_usage_window=lambda *_args: (1.0, 10),
    )

    assert report.candidates[0].category == "thread_unresolved"


def test_cost_audit_flags_missing_usage_data(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "No usage in window",
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
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=state_path,
        codex_logs_path=logs_path,
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: "thread-1",
        resolve_usage_window=lambda *_args: (None, None),
    )

    assert report.candidates[0].category == "no_usage_data_found"


def test_cost_audit_flags_sync_gap_when_usage_is_recoverable(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Recoverable usage",
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
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=state_path,
        codex_logs_path=logs_path,
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: "thread-1",
        resolve_usage_window=lambda *_args: (0.25, 1234),
    )

    assert report.candidates[0].category == "sync_gap"


def test_cost_audit_flags_partial_stored_coverage(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    report = audit_cost_coverage(
        {
            "goals": [
                {
                    "goal_id": "goal-1",
                    "title": "Only cost stored",
                    "goal_type": "product",
                    "supersedes_goal_id": None,
                    "status": "success",
                    "attempts": 1,
                    "started_at": "2026-03-29T09:00:00+00:00",
                    "finished_at": "2026-03-29T09:05:00+00:00",
                    "cost_usd": 0.25,
                    "tokens_total": None,
                    "failure_reason": None,
                    "notes": None,
                }
            ]
        },
        pricing_path=tmp_path / "pricing.json",
        codex_state_path=state_path,
        codex_logs_path=logs_path,
        cwd=tmp_path,
        codex_thread_id=None,
        find_thread_id=lambda _state, _cwd, _thread_id: "thread-1",
        resolve_usage_window=lambda *_args: (0.25, 1234),
    )

    assert report.candidates[0].category == "partial_stored_coverage"


def test_render_cost_audit_report_groups_candidates(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    rendered = render_cost_audit_report(
        audit_cost_coverage(
            {
                "goals": [
                    {
                        "goal_id": "goal-1",
                        "title": "Recoverable usage",
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
                    },
                    {
                        "goal_id": "goal-2",
                        "title": "No timestamps",
                        "goal_type": "product",
                        "supersedes_goal_id": None,
                        "status": "success",
                        "attempts": 1,
                        "started_at": None,
                        "finished_at": "2026-03-29T09:05:00+00:00",
                        "cost_usd": None,
                        "tokens_total": None,
                        "failure_reason": None,
                        "notes": None,
                    },
                ]
            },
            pricing_path=tmp_path / "pricing.json",
            codex_state_path=state_path,
            codex_logs_path=logs_path,
            cwd=tmp_path,
            codex_thread_id=None,
            find_thread_id=lambda _state, _cwd, _thread_id: "thread-1",
            resolve_usage_window=lambda *_args: (0.25, 1234),
        )
    )

    assert "Cost coverage audit" in rendered
    assert "[sync_gap]" in rendered
    assert "[incomplete_goal_window]" in rendered


def test_render_cost_audit_report_for_empty_candidates_is_concise(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    logs_path = tmp_path / "logs.sqlite"
    state_path.touch()
    logs_path.touch()

    rendered = render_cost_audit_report(
        audit_cost_coverage(
            {
                "goals": [
                    {
                        "goal_id": "goal-1",
                        "title": "Fully covered",
                        "goal_type": "product",
                        "supersedes_goal_id": None,
                        "status": "success",
                        "attempts": 1,
                        "started_at": "2026-03-29T09:00:00+00:00",
                        "finished_at": "2026-03-29T09:05:00+00:00",
                        "cost_usd": 0.25,
                        "tokens_total": 1234,
                        "failure_reason": None,
                        "notes": None,
                    }
                ]
            },
            pricing_path=tmp_path / "pricing.json",
            codex_state_path=state_path,
            codex_logs_path=logs_path,
            cwd=tmp_path,
            codex_thread_id=None,
            find_thread_id=lambda _state, _cwd, _thread_id: "thread-1",
            resolve_usage_window=lambda *_args: (0.25, 1234),
        )
    )

    assert "_All closed product goals have stored cost and token coverage._" in rendered
