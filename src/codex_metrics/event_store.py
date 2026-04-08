"""Append-only NDJSON event store for codex-metrics.

Each event is one JSON line in ``metrics/events.ndjson`` with these fields:

- ``event_type``: one of the EVENT_TYPES constants
- ``ts``: ISO 8601 UTC timestamp of the write
- ``goal``: full GoalRecord dict (single-goal events and usage_synced)
- ``entries``: list of AttemptEntryRecord dicts affected by this event
- ``goals``: list of GoalRecord dicts (usage_synced bulk updates)
- ``dropped_goal_id``: goal_id removed from the log (goals_merged)

Replay is last-write-wins per goal_id / entry_id, processed in file order.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "goal_started",
        "goal_continued",
        "goal_finished",
        "goal_updated",
        "goals_merged",
        "usage_synced",
    }
)

_SINGLE_GOAL_EVENTS: frozenset[str] = frozenset(
    {"goal_started", "goal_continued", "goal_finished", "goal_updated"}
)


def append_event(
    events_path: Path,
    event_type: str,
    *,
    goal: dict[str, Any] | None = None,
    entries: list[dict[str, Any]] | None = None,
    goals: list[dict[str, Any]] | None = None,
    dropped_goal_id: str | None = None,
    ts: str | None = None,
) -> None:
    """Append one event line to the NDJSON event log.

    For single-goal events (goal_started / continued / finished / updated):
      pass ``goal`` and optionally ``entries``.

    For goals_merged:
      pass ``goal`` (the kept goal), ``entries`` (kept goal's entries), and
      ``dropped_goal_id``.

    For usage_synced:
      pass a single ``goal`` for one-task updates, or ``goals`` for bulk.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type!r}. Must be one of {sorted(EVENT_TYPES)}")

    if ts is None:
        from codex_metrics.domain.time_utils import now_utc_iso

        ts = now_utc_iso()

    event: dict[str, Any] = {"event_type": event_type, "ts": ts}

    if goal is not None:
        event["goal"] = goal
    if entries is not None:
        event["entries"] = entries
    if goals is not None:
        event["goals"] = goals
    if dropped_goal_id is not None:
        event["dropped_goal_id"] = dropped_goal_id

    events_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(line)


def replay_events(events_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Replay all events and return ``(goals_list, entries_list)``.

    Uses last-write-wins per ``goal_id`` / ``entry_id``, processing events in
    file order (oldest first).  Returns empty lists when the file does not exist
    or is empty.
    """
    if not events_path.exists():
        return [], []

    goals: dict[str, dict[str, Any]] = {}
    entries: dict[str, dict[str, Any]] = {}

    with events_path.open("r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {events_path} at line {line_num}: {exc}"
                ) from exc

            event_type = event.get("event_type", "")

            if event_type in _SINGLE_GOAL_EVENTS:
                goal = event.get("goal")
                if goal and "goal_id" in goal:
                    goals[goal["goal_id"]] = goal
                for entry in event.get("entries") or []:
                    if "entry_id" in entry:
                        entries[entry["entry_id"]] = entry

            elif event_type == "goals_merged":
                kept_goal = event.get("goal")
                if kept_goal and "goal_id" in kept_goal:
                    goals[kept_goal["goal_id"]] = kept_goal
                dropped = event.get("dropped_goal_id")
                if dropped:
                    goals.pop(dropped, None)
                # Any downstream goals that had supersession links rewritten
                for g in event.get("goals") or []:
                    if "goal_id" in g:
                        goals[g["goal_id"]] = g
                for entry in event.get("entries") or []:
                    if "entry_id" in entry:
                        entries[entry["entry_id"]] = entry

            elif event_type == "usage_synced":
                single_goal = event.get("goal")
                if single_goal and "goal_id" in single_goal:
                    goals[single_goal["goal_id"]] = single_goal
                for g in event.get("goals") or []:
                    if "goal_id" in g:
                        goals[g["goal_id"]] = g
                for entry in event.get("entries") or []:
                    if "entry_id" in entry:
                        entries[entry["entry_id"]] = entry

    goals_list = sorted(goals.values(), key=lambda g: g.get("goal_id", ""))
    entries_list = sorted(entries.values(), key=lambda e: e.get("entry_id", ""))

    return goals_list, entries_list
