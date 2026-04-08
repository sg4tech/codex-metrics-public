from __future__ import annotations

from pathlib import Path

from codex_metrics.domain import load_metrics
from codex_metrics.event_store import append_event, replay_events


def _goal_dict(**overrides: object) -> dict:
    values: dict = {
        "goal_id": "2026-04-07-001",
        "title": "Keep metrics readable",
        "goal_type": "meta",
        "supersedes_goal_id": None,
        "status": "success",
        "attempts": 1,
        "started_at": "2026-04-07T10:00:00+00:00",
        "finished_at": "2026-04-07T10:01:00+00:00",
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
    values.update(overrides)
    return values


def test_append_and_replay_single_goal(tmp_path: Path) -> None:
    events_path = tmp_path / "metrics" / "events.ndjson"
    goal = _goal_dict()

    append_event(events_path, "goal_started", goal=goal, entries=[])

    goals_list, entries_list = replay_events(events_path)
    assert len(goals_list) == 1
    assert goals_list[0]["goal_id"] == "2026-04-07-001"
    assert goals_list[0]["notes"] == "Round-trip check"
    assert entries_list == []


def test_append_creates_parent_directory(tmp_path: Path) -> None:
    events_path = tmp_path / "nested" / "metrics" / "events.ndjson"
    append_event(events_path, "goal_updated", goal=_goal_dict(), entries=[])
    assert events_path.exists()
    assert events_path.parent.is_dir()


def test_replay_empty_file_returns_empty_lists(tmp_path: Path) -> None:
    events_path = tmp_path / "metrics" / "events.ndjson"
    events_path.parent.mkdir(parents=True)
    events_path.write_text("", encoding="utf-8")

    goals, entries = replay_events(events_path)
    assert goals == []
    assert entries == []


def test_replay_missing_file_returns_empty_lists(tmp_path: Path) -> None:
    events_path = tmp_path / "metrics" / "events.ndjson"
    goals, entries = replay_events(events_path)
    assert goals == []
    assert entries == []


def test_last_write_wins_per_goal_id(tmp_path: Path) -> None:
    events_path = tmp_path / "metrics" / "events.ndjson"
    first = _goal_dict(notes="first version")
    second = _goal_dict(notes="second version")

    append_event(events_path, "goal_started", goal=first, entries=[])
    append_event(events_path, "goal_updated", goal=second, entries=[])

    goals, _ = replay_events(events_path)
    assert len(goals) == 1
    assert goals[0]["notes"] == "second version"


def test_goals_merged_removes_dropped_goal(tmp_path: Path) -> None:
    events_path = tmp_path / "metrics" / "events.ndjson"
    kept = _goal_dict(goal_id="2026-04-07-001", title="Kept")
    dropped = _goal_dict(goal_id="2026-04-07-002", title="Dropped")

    append_event(events_path, "goal_started", goal=kept, entries=[])
    append_event(events_path, "goal_started", goal=dropped, entries=[])
    append_event(events_path, "goals_merged", goal=kept, entries=[], dropped_goal_id="2026-04-07-002")

    goals, _ = replay_events(events_path)
    assert len(goals) == 1
    assert goals[0]["goal_id"] == "2026-04-07-001"


def test_load_metrics_round_trip(tmp_path: Path) -> None:
    events_path = tmp_path / "metrics" / "events.ndjson"
    goal = _goal_dict()
    append_event(events_path, "goal_started", goal=goal, entries=[])

    data = load_metrics(events_path)
    assert len(data["goals"]) == 1
    assert data["goals"][0]["goal_id"] == "2026-04-07-001"
    assert "summary" in data
