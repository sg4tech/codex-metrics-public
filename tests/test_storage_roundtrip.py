from __future__ import annotations

from pathlib import Path

from codex_metrics import storage
from codex_metrics.domain import load_metrics


def _unlock_metrics_file(path: Path) -> None:
    commands = storage._immutability_command()
    if commands is None or not path.exists():
        return
    unlock_command, _ = commands
    try:
        storage._run_file_immutability_command(unlock_command, path)
    except Exception:
        pass


def test_save_metrics_writes_and_load_metrics_reads_back(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    payload = {
        "summary": {"closed_tasks": 1},
        "goals": [
            {
                "goal_id": "goal-1",
                "title": "Keep metrics readable",
                "goal_type": "meta",
                "supersedes_goal_id": None,
                "status": "success",
                "attempts": 1,
                "started_at": "2026-04-03T10:00:00+00:00",
                "finished_at": "2026-04-03T10:01:00+00:00",
                "cost_usd": None,
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "tokens_total": None,
                "failure_reason": None,
                "notes": "Round-trip check",
                "agent_name": None,
                "result_fit": None,
                "model": None,
            }
        ],
        "entries": [],
    }

    storage.save_metrics(metrics_path, payload)

    assert metrics_path.exists()
    loaded = load_metrics(metrics_path)
    assert loaded["summary"] == payload["summary"]
    assert loaded["goals"][0]["goal_id"] == "goal-1"
    assert loaded["goals"][0]["notes"] == "Round-trip check"
    _unlock_metrics_file(metrics_path)


def test_save_metrics_creates_parent_directory(tmp_path: Path) -> None:
    metrics_path = tmp_path / "nested" / "metrics" / "codex_metrics.json"

    storage.save_metrics(
        metrics_path,
        {
            "summary": {},
            "goals": [],
            "entries": [],
        },
    )

    assert metrics_path.exists()
    assert metrics_path.parent.is_dir()
    _unlock_metrics_file(metrics_path)
