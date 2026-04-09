from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_agents_metrics.domain.time_utils import now_utc_datetime


def next_entry_id(entries: list[dict[str, Any]], goal_id: str) -> str:
    existing_ids = {entry["entry_id"] for entry in entries}
    entry_number = 1
    while True:
        candidate = f"{goal_id}-attempt-{entry_number:03d}"
        if candidate not in existing_ids:
            return candidate
        entry_number += 1


def next_goal_id(tasks: list[dict[str, Any]], now: datetime | None = None) -> str:
    current_time = now or now_utc_datetime()
    date_prefix = current_time.date().isoformat()
    prefix = f"{date_prefix}-"
    max_suffix = 0

    for task in tasks:
        goal_id = task.get("goal_id")
        if not isinstance(goal_id, str) or not goal_id.startswith(prefix):
            continue
        suffix = goal_id.removeprefix(prefix)
        if len(suffix) != 3 or not suffix.isdigit():
            continue
        max_suffix = max(max_suffix, int(suffix))

    return f"{date_prefix}-{max_suffix + 1:03d}"
