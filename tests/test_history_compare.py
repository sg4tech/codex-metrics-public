from __future__ import annotations

import sqlite3
import sys
from argparse import Namespace
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_metrics.commands import handle_compare_metrics_to_history
from codex_metrics.domain import default_metrics, recompute_summary
from codex_metrics.history_compare import compare_metrics_to_history, render_history_compare_report


def _build_metrics_data() -> dict[str, object]:
    data = default_metrics()
    data["goals"] = [
        {
            "goal_id": "2026-04-02-001",
            "title": "Recent product goal",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 2,
            "started_at": "2026-04-02T10:00:00+00:00",
            "finished_at": "2026-04-02T10:10:00+00:00",
            "cost_usd": 1.2,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "tokens_total": 1000,
            "failure_reason": None,
            "notes": "Needed one retry",
            "result_fit": "partial_fit",
            "model": None,
        },
        {
            "goal_id": "2026-04-02-002",
            "title": "Stable meta goal",
            "goal_type": "meta",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-04-02T11:00:00+00:00",
            "finished_at": "2026-04-02T11:05:00+00:00",
            "cost_usd": None,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "tokens_total": None,
            "failure_reason": None,
            "notes": None,
            "result_fit": None,
            "model": None,
        },
    ]
    recompute_summary(data)
    return data


def _create_compare_warehouse(path: Path, *, repo_cwd: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE derived_goals (
                thread_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                cwd TEXT,
                model_provider TEXT,
                model TEXT,
                title TEXT,
                archived INTEGER,
                session_count INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL,
                retry_count INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                usage_event_count INTEGER NOT NULL,
                log_count INTEGER NOT NULL,
                timeline_event_count INTEGER NOT NULL,
                first_seen_at TEXT,
                last_seen_at TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_usage_slices (
                usage_slice_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                session_path TEXT NOT NULL,
                attempt_index INTEGER NOT NULL,
                usage_event_count INTEGER NOT NULL,
                input_tokens INTEGER,
                cached_input_tokens INTEGER,
                output_tokens INTEGER,
                reasoning_output_tokens INTEGER,
                total_tokens INTEGER,
                first_usage_at TEXT,
                last_usage_at TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_projects (
                project_cwd TEXT PRIMARY KEY,
                thread_count INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL,
                retry_thread_count INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                usage_event_count INTEGER NOT NULL,
                log_count INTEGER NOT NULL,
                timeline_event_count INTEGER NOT NULL,
                input_tokens INTEGER,
                cached_input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                first_seen_at TEXT,
                last_seen_at TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO derived_goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-repo-1",
                "/tmp/source-1",
                str(repo_cwd.resolve()),
                "openai",
                "gpt-5.4-mini",
                "Repo thread",
                0,
                1,
                1,
                0,
                5,
                1,
                1,
                8,
                "2026-04-02T10:00:00Z",
                "2026-04-02T10:05:00Z",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-other-1",
                "/tmp/source-2",
                "/tmp/other-project",
                "openai",
                "gpt-5.4-mini",
                "Other thread",
                0,
                1,
                1,
                0,
                0,
                0,
                1,
                1,
                "2026-04-02T09:00:00Z",
                "2026-04-02T09:05:00Z",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_usage_slices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "usage-1",
                "thread-repo-1",
                "/tmp/source-1",
                "/tmp/session-1",
                1,
                1,
                120,
                30,
                20,
                5,
                170,
                "2026-04-02T10:00:00Z",
                "2026-04-02T10:05:00Z",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(repo_cwd.resolve()),
                1,
                1,
                0,
                5,
                1,
                1,
                8,
                120,
                30,
                20,
                170,
                "2026-04-02T10:00:00Z",
                "2026-04-02T10:05:00Z",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/spendsave",
                1,
                1,
                0,
                0,
                0,
                0,
                1,
                None,
                None,
                None,
                None,
                "2026-04-02T09:00:00Z",
                "2026-04-02T09:05:00Z",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/invest",
                1,
                2,
                1,
                8,
                2,
                1,
                12,
                220,
                45,
                60,
                325,
                "2026-04-02T12:00:00Z",
                "2026-04-02T12:10:00Z",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO derived_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/hhsave",
                1,
                1,
                0,
                3,
                1,
                1,
                5,
                40,
                5,
                10,
                55,
                "2026-04-02T13:00:00Z",
                "2026-04-02T13:05:00Z",
                "{}",
            ),
        )
        conn.commit()


def test_compare_metrics_to_history_reports_scope_and_breakdown_gaps(tmp_path: Path) -> None:
    warehouse_path = tmp_path / "history.sqlite"
    repo_cwd = tmp_path / "codex-metrics"
    repo_cwd.mkdir()
    _create_compare_warehouse(warehouse_path, repo_cwd=repo_cwd)

    report = compare_metrics_to_history(
        _build_metrics_data(),
        warehouse_path=warehouse_path,
        cwd=repo_cwd,
        metrics_path=tmp_path / "metrics.json",
    )

    assert report.ledger_closed_goal_count == 2
    assert report.ledger_attempts_gt_one == 1
    assert report.warehouse_global.projects == 4
    assert report.warehouse_project.threads == 1
    assert report.warehouse_project.projects == 1
    assert report.warehouse_project.usage_threads == 1
    assert report.warehouse_project.total_tokens == 170
    assert len(report.warehouse_projects) == 4
    project_by_name = {Path(summary.project_cwd).name: summary for summary in report.warehouse_projects}
    assert set(project_by_name) == {
        "codex-metrics",
        "spendsave",
        "invest",
        "hhsave",
    }
    assert project_by_name["codex-metrics"].threads == 1
    assert project_by_name["codex-metrics"].attempts == 1
    assert project_by_name["codex-metrics"].message_count == 5
    assert project_by_name["codex-metrics"].usage_event_count == 1
    assert project_by_name["codex-metrics"].log_count == 1
    assert project_by_name["codex-metrics"].timeline_event_count == 8
    assert project_by_name["invest"].message_count == 8
    assert project_by_name["invest"].usage_event_count == 2
    assert project_by_name["hhsave"].message_count == 3
    assert project_by_name["spendsave"].message_count == 0
    categories = {finding.category for finding in report.findings}
    assert "subset_scope" in categories
    assert "retry_mismatch" in categories
    assert "breakdown_gap" in categories
    assert "transcript_strength" in categories

    rendered = render_history_compare_report(report)
    assert "Ledger vs History Compare" in rendered
    assert "[warehouse_project]" in rendered
    assert "[warehouse_projects]" in rendered
    assert "codex-metrics" in rendered
    assert "spendsave" in rendered
    assert "invest" in rendered
    assert "hhsave" in rendered
    assert "retry_mismatch" in rendered


def test_compare_metrics_to_history_lists_all_projects_without_truncation(tmp_path: Path) -> None:
    warehouse_path = tmp_path / "history.sqlite"
    repo_cwd = tmp_path / "codex-metrics"
    repo_cwd.mkdir()
    _create_compare_warehouse(warehouse_path, repo_cwd=repo_cwd)

    with sqlite3.connect(warehouse_path) as conn:
        for index in range(7):
            project_cwd = f"/tmp/extra-project-{index}"
            conn.execute(
                """
                INSERT INTO derived_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_cwd,
                    1,
                    1,
                    0,
                    1,
                    1,
                    0,
                    1,
                    10 + index,
                    0,
                    0,
                    10 + index,
                    f"2026-04-02T14:0{index}:00Z",
                    f"2026-04-02T14:0{index}:30Z",
                    "{}",
                ),
            )
        conn.commit()

    report = compare_metrics_to_history(
        _build_metrics_data(),
        warehouse_path=warehouse_path,
        cwd=repo_cwd,
        metrics_path=tmp_path / "metrics.json",
    )

    assert len(report.warehouse_projects) == 11
    assert {Path(summary.project_cwd).name for summary in report.warehouse_projects} >= {
        "codex-metrics",
        "spendsave",
        "invest",
        "hhsave",
    }

    rendered = render_history_compare_report(report)
    assert "[warehouse_project_classes]" not in rendered


def test_compare_metrics_command_handler_prints_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    warehouse_path = tmp_path / "history.sqlite"
    repo_cwd = tmp_path / "codex-metrics"
    repo_cwd.mkdir()
    _create_compare_warehouse(warehouse_path, repo_cwd=repo_cwd)

    class DummyRuntime:
        def load_metrics(self, path: Path) -> dict[str, object]:
            assert path == tmp_path / "metrics.json"
            return _build_metrics_data()

        def compare_metrics_to_history(
            self,
            data: dict[str, object],
            *,
            warehouse_path: Path,
            cwd: Path,
            metrics_path: Path,
        ):
            return compare_metrics_to_history(
                data,
                warehouse_path=warehouse_path,
                cwd=cwd,
                metrics_path=metrics_path,
            )

        def render_history_compare_report(self, report) -> str:
            return render_history_compare_report(report)

    exit_code = handle_compare_metrics_to_history(
        Namespace(
            metrics_path=str(tmp_path / "metrics.json"),
            warehouse_path=str(warehouse_path),
            cwd=str(repo_cwd),
        ),
        DummyRuntime(),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Ledger vs History Compare" in captured.out
    assert "[warehouse_projects]" in captured.out
    assert "[warehouse_project_classes]" not in captured.out


def test_compare_metrics_to_history_rejects_non_derived_warehouse(tmp_path: Path) -> None:
    warehouse_path = tmp_path / "raw.sqlite"
    sqlite3.connect(warehouse_path).close()

    try:
        compare_metrics_to_history(
            _build_metrics_data(),
            warehouse_path=warehouse_path,
            cwd=tmp_path,
            metrics_path=tmp_path / "metrics.json",
        )
    except ValueError as exc:
        assert "run derive-codex-history first" in str(exc)
    else:
        raise AssertionError("Expected compare_metrics_to_history to reject a non-derived warehouse")
