from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from codex_metrics.domain import EffectiveGoalRecord, build_effective_goals, goal_from_dict
from codex_metrics.reporting import format_pct, format_usd


@dataclass(frozen=True)
class RetroTimelineEvent:
    retro_event_id: str
    message_id: str
    thread_id: str | None
    session_path: str
    event_index: int
    message_index: int
    message_role: str
    event_time: str
    event_date: str
    project_cwd: str
    retro_file_path: str
    title: str
    summary: str | None
    source_kind: str
    raw_json: str


@dataclass(frozen=True)
class RetroMetricWindow:
    window_id: str
    retro_event_id: str
    window_side: str
    window_strategy: str
    window_size: int
    anchor_time: str
    window_start_time: str | None
    window_end_time: str | None
    product_goals_closed: int
    product_success_rate: float | None
    review_coverage: float | None
    exact_fit_rate: float | None
    partial_fit_rate: float | None
    miss_rate: float | None
    attempts_per_closed_product_goal: float | None
    known_cost_per_success_usd: float | None
    known_cost_coverage: float | None
    failure_reason_summary: str | None
    goal_ids_json: str
    raw_json: str


@dataclass(frozen=True)
class RetroWindowDelta:
    retro_event_id: str
    window_strategy: str
    window_size: int
    before_product_goals_closed: int
    after_product_goals_closed: int
    delta_product_success_rate: float | None
    delta_exact_fit_rate: float | None
    delta_partial_fit_rate: float | None
    delta_miss_rate: float | None
    delta_attempts_per_closed_product_goal: float | None
    delta_known_cost_per_success_usd: float | None
    delta_known_cost_coverage: float | None
    raw_json: str


@dataclass(frozen=True)
class RetroTimelineRecord:
    event: RetroTimelineEvent
    before_window: RetroMetricWindow
    after_window: RetroMetricWindow
    delta: RetroWindowDelta


@dataclass(frozen=True)
class RetroTimelineReport:
    metrics_path: Path
    warehouse_path: Path
    cwd: Path
    window_size: int
    events: list[RetroTimelineEvent]
    windows: list[RetroMetricWindow]
    deltas: list[RetroWindowDelta]
    records: list[RetroTimelineRecord]


def _goal_timestamp(goal: EffectiveGoalRecord) -> str | None:
    return goal.finished_at or goal.started_at


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _normalize_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _compact_text(value: str | None, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}…"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _numeric_delta(after_value: float | None, before_value: float | None) -> float | None:
    if after_value is None or before_value is None:
        return None
    return after_value - before_value


def _effective_goals_from_data(data: dict[str, Any]) -> list[EffectiveGoalRecord]:
    return build_effective_goals([goal_from_dict(goal) for goal in data.get("goals", [])])


_RETRO_MESSAGE_PATH_PATTERN = re.compile(r"docs/retros/[^)\]\s]+\.md", re.IGNORECASE)


def _title_from_retro_path(retro_file_path: str) -> str:
    stem = Path(retro_file_path).stem
    match = re.match(r"^\d{4}-\d{2}-\d{2}-(.+)$", stem)
    cleaned = match.group(1) if match is not None else stem
    return cleaned.replace("-", " ").strip() or stem


def _extract_retro_paths(message_text: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in _RETRO_MESSAGE_PATH_PATTERN.findall(message_text):
        normalized = match.strip().rstrip(".,;:")
        if normalized not in seen:
            seen.add(normalized)
            paths.append(normalized)
    return paths


def _load_retro_events_from_messages(conn: sqlite3.Connection, *, cwd: Path) -> list[RetroTimelineEvent]:
    try:
        message_rows = conn.execute(
            """
            SELECT
                m.message_id,
                m.thread_id,
                m.session_path,
                m.source_path,
                m.event_index,
                m.message_index,
                m.role,
                m.text,
                m.timestamp
            FROM main.normalized_messages AS m
            JOIN main.normalized_threads AS t ON t.thread_id = m.thread_id
            WHERE t.cwd = ? AND m.role = 'assistant' AND lower(m.text) LIKE '%docs/retros/%'
            ORDER BY m.timestamp, m.thread_id, m.session_path, m.event_index, m.message_index
            """,
            (str(cwd.resolve()),),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(
            "Warehouse does not contain main.normalized_messages; run normalize-codex-history first"
        ) from exc

    events_by_path: dict[str, RetroTimelineEvent] = {}
    for row in message_rows:
        timestamp = _normalize_timestamp(row["timestamp"])
        if timestamp is None:
            continue
        retro_paths = _extract_retro_paths(row["text"])
        if not retro_paths:
            continue
        for retro_path in retro_paths:
            if retro_path in events_by_path:
                continue
            raw_payload = {
                "message_id": row["message_id"],
                "thread_id": row["thread_id"],
                "session_path": row["session_path"],
                "source_path": row["source_path"],
                "event_index": row["event_index"],
                "message_index": row["message_index"],
                "role": row["role"],
                "timestamp": timestamp,
                "retro_file_path": retro_path,
                "text": row["text"],
                "source_kind": "message",
            }
            events_by_path[retro_path] = RetroTimelineEvent(
                retro_event_id=f"retro-event:{Path(retro_path).stem}",
                message_id=row["message_id"],
                thread_id=row["thread_id"],
                session_path=row["session_path"],
                event_index=int(row["event_index"]),
                message_index=int(row["message_index"]),
                message_role=row["role"],
                event_time=timestamp,
                event_date=timestamp[:10],
                project_cwd=str(cwd.resolve()),
                retro_file_path=retro_path,
                title=_title_from_retro_path(retro_path),
                summary=_compact_text(row["text"], limit=180),
                source_kind="message",
                raw_json=_json_dumps(raw_payload),
            )
    return sorted(events_by_path.values(), key=lambda event: (_parse_timestamp(event.event_time), event.retro_event_id))


def _build_window(
    *,
    retro_event_id: str,
    window_side: str,
    window_size: int,
    anchor_time: str,
    goals: list[EffectiveGoalRecord],
) -> RetroMetricWindow:
    closed_goal_count = len(goals)
    successful_goals = [goal for goal in goals if goal.status == "success"]
    reviewed_goals = [goal for goal in goals if goal.result_fit is not None]
    exact_fit_goals = [goal for goal in reviewed_goals if goal.result_fit == "exact_fit"]
    partial_fit_goals = [goal for goal in reviewed_goals if goal.result_fit == "partial_fit"]
    miss_goals = [goal for goal in reviewed_goals if goal.result_fit == "miss"]
    failed_goals = [goal for goal in goals if goal.status == "fail"]
    known_cost_successes = [goal for goal in successful_goals if goal.cost_usd_known is not None]

    failure_reason_counts: dict[str, int] = {}
    for goal in failed_goals:
        if goal.failure_reason is None:
            continue
        failure_reason_counts[goal.failure_reason] = failure_reason_counts.get(goal.failure_reason, 0) + 1

    goal_timestamps = [timestamp for goal in goals if (timestamp := _goal_timestamp(goal)) is not None]
    known_cost_total = sum(goal.cost_usd_known or 0.0 for goal in known_cost_successes)
    raw_payload = {
        "retro_event_id": retro_event_id,
        "window_side": window_side,
        "window_strategy": "product_goals_count",
        "window_size": window_size,
        "anchor_time": anchor_time,
        "goal_ids": [goal.goal_id for goal in goals],
        "failure_reason_counts": failure_reason_counts,
    }
    return RetroMetricWindow(
        window_id=f"{retro_event_id}:{window_side}:{window_size}",
        retro_event_id=retro_event_id,
        window_side=window_side,
        window_strategy="product_goals_count",
        window_size=window_size,
        anchor_time=anchor_time,
        window_start_time=min(goal_timestamps) if goal_timestamps else None,
        window_end_time=max(goal_timestamps) if goal_timestamps else None,
        product_goals_closed=closed_goal_count,
        product_success_rate=(len(successful_goals) / closed_goal_count) if closed_goal_count else None,
        review_coverage=(len(reviewed_goals) / closed_goal_count) if closed_goal_count else None,
        exact_fit_rate=(len(exact_fit_goals) / len(reviewed_goals)) if reviewed_goals else None,
        partial_fit_rate=(len(partial_fit_goals) / len(reviewed_goals)) if reviewed_goals else None,
        miss_rate=(len(miss_goals) / len(reviewed_goals)) if reviewed_goals else None,
        attempts_per_closed_product_goal=(
            sum(goal.attempts for goal in goals) / closed_goal_count if closed_goal_count else None
        ),
        known_cost_per_success_usd=(
            known_cost_total / len(known_cost_successes) if known_cost_successes else None
        ),
        known_cost_coverage=(len(known_cost_successes) / len(successful_goals)) if successful_goals else None,
        failure_reason_summary=_json_dumps(failure_reason_counts) if failure_reason_counts else None,
        goal_ids_json=_json_dumps([goal.goal_id for goal in goals]),
        raw_json=_json_dumps(raw_payload),
    )


def _build_delta(before_window: RetroMetricWindow, after_window: RetroMetricWindow) -> RetroWindowDelta:
    raw_payload = {
        "retro_event_id": before_window.retro_event_id,
        "window_strategy": before_window.window_strategy,
        "window_size": before_window.window_size,
        "before_product_goals_closed": before_window.product_goals_closed,
        "after_product_goals_closed": after_window.product_goals_closed,
    }
    return RetroWindowDelta(
        retro_event_id=before_window.retro_event_id,
        window_strategy=before_window.window_strategy,
        window_size=before_window.window_size,
        before_product_goals_closed=before_window.product_goals_closed,
        after_product_goals_closed=after_window.product_goals_closed,
        delta_product_success_rate=_numeric_delta(after_window.product_success_rate, before_window.product_success_rate),
        delta_exact_fit_rate=_numeric_delta(after_window.exact_fit_rate, before_window.exact_fit_rate),
        delta_partial_fit_rate=_numeric_delta(after_window.partial_fit_rate, before_window.partial_fit_rate),
        delta_miss_rate=_numeric_delta(after_window.miss_rate, before_window.miss_rate),
        delta_attempts_per_closed_product_goal=_numeric_delta(
            after_window.attempts_per_closed_product_goal,
            before_window.attempts_per_closed_product_goal,
        ),
        delta_known_cost_per_success_usd=_numeric_delta(
            after_window.known_cost_per_success_usd,
            before_window.known_cost_per_success_usd,
        ),
        delta_known_cost_coverage=_numeric_delta(after_window.known_cost_coverage, before_window.known_cost_coverage),
        raw_json=_json_dumps(raw_payload),
    )


def build_retro_timeline_report(
    data: dict[str, Any],
    *,
    warehouse_path: Path,
    cwd: Path,
    metrics_path: Path,
    window_size: int,
) -> RetroTimelineReport:
    if window_size <= 0:
        raise ValueError("window_size must be positive")

    effective_goals = _effective_goals_from_data(data)
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        retro_events = _load_retro_events_from_messages(conn, cwd=cwd)
    product_goals = [
        goal
        for goal in effective_goals
        if goal.goal_type == "product" and goal.status in {"success", "fail"} and _goal_timestamp(goal) is not None
    ]
    product_goals = sorted(product_goals, key=lambda goal: (_goal_timestamp(goal) or "", goal.goal_id))

    windows: list[RetroMetricWindow] = []
    deltas: list[RetroWindowDelta] = []
    records: list[RetroTimelineRecord] = []
    for event in retro_events:
        before_goals = [goal for goal in product_goals if (_goal_timestamp(goal) or "") < event.event_time][-window_size:]
        after_goals = [goal for goal in product_goals if (_goal_timestamp(goal) or "") > event.event_time][:window_size]
        before_window = _build_window(
            retro_event_id=event.retro_event_id,
            window_side="before",
            window_size=window_size,
            anchor_time=event.event_time,
            goals=before_goals,
        )
        after_window = _build_window(
            retro_event_id=event.retro_event_id,
            window_side="after",
            window_size=window_size,
            anchor_time=event.event_time,
            goals=after_goals,
        )
        delta = _build_delta(before_window, after_window)
        windows.extend([before_window, after_window])
        deltas.append(delta)
        records.append(RetroTimelineRecord(event=event, before_window=before_window, after_window=after_window, delta=delta))

    return RetroTimelineReport(
        metrics_path=metrics_path,
        warehouse_path=warehouse_path,
        cwd=cwd.resolve(),
        window_size=window_size,
        events=retro_events,
        windows=windows,
        deltas=deltas,
        records=records,
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retro_timeline_events (
            retro_event_id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            thread_id TEXT,
            session_path TEXT NOT NULL,
            event_index INTEGER NOT NULL,
            message_index INTEGER NOT NULL,
            message_role TEXT NOT NULL,
            event_time TEXT NOT NULL,
            event_date TEXT NOT NULL,
            project_cwd TEXT NOT NULL,
            retro_file_path TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            source_kind TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retro_metric_windows (
            window_id TEXT PRIMARY KEY,
            retro_event_id TEXT NOT NULL,
            window_side TEXT NOT NULL,
            window_strategy TEXT NOT NULL,
            window_size INTEGER NOT NULL,
            anchor_time TEXT NOT NULL,
            window_start_time TEXT,
            window_end_time TEXT,
            product_goals_closed INTEGER NOT NULL,
            product_success_rate REAL,
            review_coverage REAL,
            exact_fit_rate REAL,
            partial_fit_rate REAL,
            miss_rate REAL,
            attempts_per_closed_product_goal REAL,
            known_cost_per_success_usd REAL,
            known_cost_coverage REAL,
            failure_reason_summary TEXT,
            goal_ids_json TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retro_window_deltas (
            retro_event_id TEXT PRIMARY KEY,
            window_strategy TEXT NOT NULL,
            window_size INTEGER NOT NULL,
            before_product_goals_closed INTEGER NOT NULL,
            after_product_goals_closed INTEGER NOT NULL,
            delta_product_success_rate REAL,
            delta_exact_fit_rate REAL,
            delta_partial_fit_rate REAL,
            delta_miss_rate REAL,
            delta_attempts_per_closed_product_goal REAL,
            delta_known_cost_per_success_usd REAL,
            delta_known_cost_coverage REAL,
            raw_json TEXT NOT NULL
        )
        """
    )


def persist_retro_timeline_report(report: RetroTimelineReport) -> None:
    report.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(report.warehouse_path) as conn:
        _ensure_schema(conn)
        conn.execute("DROP TABLE IF EXISTS retro_timeline_events")
        conn.execute("DROP TABLE IF EXISTS retro_metric_windows")
        conn.execute("DROP TABLE IF EXISTS retro_window_deltas")
        _ensure_schema(conn)
        conn.execute("DELETE FROM retro_timeline_events")
        conn.execute("DELETE FROM retro_metric_windows")
        conn.execute("DELETE FROM retro_window_deltas")

        conn.executemany(
            """
            INSERT INTO retro_timeline_events (
                retro_event_id, message_id, thread_id, session_path, event_index, message_index,
                message_role, event_time, event_date, project_cwd, retro_file_path, title, summary,
                source_kind, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event.retro_event_id,
                    event.message_id,
                    event.thread_id,
                    event.session_path,
                    event.event_index,
                    event.message_index,
                    event.message_role,
                    event.event_time,
                    event.event_date,
                    event.project_cwd,
                    event.retro_file_path,
                    event.title,
                    event.summary,
                    event.source_kind,
                    event.raw_json,
                )
                for event in report.events
            ],
        )
        conn.executemany(
            """
            INSERT INTO retro_metric_windows (
                window_id, retro_event_id, window_side, window_strategy, window_size, anchor_time,
                window_start_time, window_end_time, product_goals_closed, product_success_rate,
                review_coverage, exact_fit_rate, partial_fit_rate, miss_rate,
                attempts_per_closed_product_goal, known_cost_per_success_usd, known_cost_coverage,
                failure_reason_summary, goal_ids_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    window.window_id,
                    window.retro_event_id,
                    window.window_side,
                    window.window_strategy,
                    window.window_size,
                    window.anchor_time,
                    window.window_start_time,
                    window.window_end_time,
                    window.product_goals_closed,
                    window.product_success_rate,
                    window.review_coverage,
                    window.exact_fit_rate,
                    window.partial_fit_rate,
                    window.miss_rate,
                    window.attempts_per_closed_product_goal,
                    window.known_cost_per_success_usd,
                    window.known_cost_coverage,
                    window.failure_reason_summary,
                    window.goal_ids_json,
                    window.raw_json,
                )
                for window in report.windows
            ],
        )
        conn.executemany(
            """
            INSERT INTO retro_window_deltas (
                retro_event_id, window_strategy, window_size, before_product_goals_closed,
                after_product_goals_closed, delta_product_success_rate, delta_exact_fit_rate,
                delta_partial_fit_rate, delta_miss_rate, delta_attempts_per_closed_product_goal,
                delta_known_cost_per_success_usd, delta_known_cost_coverage, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    delta.retro_event_id,
                    delta.window_strategy,
                    delta.window_size,
                    delta.before_product_goals_closed,
                    delta.after_product_goals_closed,
                    delta.delta_product_success_rate,
                    delta.delta_exact_fit_rate,
                    delta.delta_partial_fit_rate,
                    delta.delta_miss_rate,
                    delta.delta_attempts_per_closed_product_goal,
                    delta.delta_known_cost_per_success_usd,
                    delta.delta_known_cost_coverage,
                    delta.raw_json,
                )
                for delta in report.deltas
            ],
        )


def derive_retro_timeline(
    data: dict[str, Any],
    *,
    warehouse_path: Path,
    cwd: Path,
    metrics_path: Path,
    window_size: int,
) -> RetroTimelineReport:
    report = build_retro_timeline_report(
        data,
        warehouse_path=warehouse_path,
        cwd=cwd,
        metrics_path=metrics_path,
        window_size=window_size,
    )
    persist_retro_timeline_report(report)
    return report


def render_retro_timeline_report(report: RetroTimelineReport) -> str:
    lines = [
        "Retrospective Timeline Report",
        "",
        f"Metrics path: {report.metrics_path}",
        f"Warehouse path: {report.warehouse_path}",
        f"Repository cwd: {report.cwd}",
        f"Retro events: {len(report.events)}",
        f"Window size: {report.window_size} product goals before/after each retro",
        "",
    ]
    if not report.records:
        lines.append("No closed retro goals with timestamps were found.")
        return "\n".join(lines)

    for record in report.records:
        lines.extend(
            [
                f"[retro] {record.event.event_time} | {record.event.title}",
                f"- retro_event_id: {record.event.retro_event_id}",
                f"- message_id: {record.event.message_id}",
                f"- source_kind: {record.event.source_kind}",
                f"- retro_file_path: {record.event.retro_file_path}",
                f"- summary: {record.event.summary or 'n/a'}",
                f"- before_goals: {record.before_window.product_goals_closed}",
                (
                    f"- before_exact_fit_rate: {format_pct(record.before_window.exact_fit_rate)} "
                    f"(review_coverage={format_pct(record.before_window.review_coverage)})"
                ),
                (
                    f"- before_attempts_per_goal: "
                    f"{record.before_window.attempts_per_closed_product_goal if record.before_window.attempts_per_closed_product_goal is not None else 'n/a'}"
                ),
                (
                    f"- before_known_cost_per_success_usd: {format_usd(record.before_window.known_cost_per_success_usd)} "
                    f"(coverage={format_pct(record.before_window.known_cost_coverage)})"
                ),
                f"- after_goals: {record.after_window.product_goals_closed}",
                (
                    f"- after_exact_fit_rate: {format_pct(record.after_window.exact_fit_rate)} "
                    f"(review_coverage={format_pct(record.after_window.review_coverage)})"
                ),
                (
                    f"- after_attempts_per_goal: "
                    f"{record.after_window.attempts_per_closed_product_goal if record.after_window.attempts_per_closed_product_goal is not None else 'n/a'}"
                ),
                (
                    f"- after_known_cost_per_success_usd: {format_usd(record.after_window.known_cost_per_success_usd)} "
                    f"(coverage={format_pct(record.after_window.known_cost_coverage)})"
                ),
                f"- delta_exact_fit_rate: {format_pct(record.delta.delta_exact_fit_rate)}",
                (
                    f"- delta_attempts_per_goal: "
                    f"{record.delta.delta_attempts_per_closed_product_goal if record.delta.delta_attempts_per_closed_product_goal is not None else 'n/a'}"
                ),
                f"- delta_known_cost_per_success_usd: {format_usd(record.delta.delta_known_cost_per_success_usd)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _event_to_dict(event: RetroTimelineEvent) -> dict[str, Any]:
    return {
        "retro_event_id": event.retro_event_id,
        "message_id": event.message_id,
        "thread_id": event.thread_id,
        "session_path": event.session_path,
        "event_index": event.event_index,
        "message_index": event.message_index,
        "message_role": event.message_role,
        "event_time": event.event_time,
        "event_date": event.event_date,
        "project_cwd": event.project_cwd,
        "retro_file_path": event.retro_file_path,
        "title": event.title,
        "summary": event.summary,
        "source_kind": event.source_kind,
        "raw_json": event.raw_json,
    }


def _window_to_dict(window: RetroMetricWindow) -> dict[str, Any]:
    return {
        "window_id": window.window_id,
        "retro_event_id": window.retro_event_id,
        "window_side": window.window_side,
        "window_strategy": window.window_strategy,
        "window_size": window.window_size,
        "anchor_time": window.anchor_time,
        "window_start_time": window.window_start_time,
        "window_end_time": window.window_end_time,
        "product_goals_closed": window.product_goals_closed,
        "product_success_rate": window.product_success_rate,
        "review_coverage": window.review_coverage,
        "exact_fit_rate": window.exact_fit_rate,
        "partial_fit_rate": window.partial_fit_rate,
        "miss_rate": window.miss_rate,
        "attempts_per_closed_product_goal": window.attempts_per_closed_product_goal,
        "known_cost_per_success_usd": window.known_cost_per_success_usd,
        "known_cost_coverage": window.known_cost_coverage,
        "failure_reason_summary": window.failure_reason_summary,
        "goal_ids_json": window.goal_ids_json,
        "raw_json": window.raw_json,
    }


def _delta_to_dict(delta: RetroWindowDelta) -> dict[str, Any]:
    return {
        "retro_event_id": delta.retro_event_id,
        "window_strategy": delta.window_strategy,
        "window_size": delta.window_size,
        "before_product_goals_closed": delta.before_product_goals_closed,
        "after_product_goals_closed": delta.after_product_goals_closed,
        "delta_product_success_rate": delta.delta_product_success_rate,
        "delta_exact_fit_rate": delta.delta_exact_fit_rate,
        "delta_partial_fit_rate": delta.delta_partial_fit_rate,
        "delta_miss_rate": delta.delta_miss_rate,
        "delta_attempts_per_closed_product_goal": delta.delta_attempts_per_closed_product_goal,
        "delta_known_cost_per_success_usd": delta.delta_known_cost_per_success_usd,
        "delta_known_cost_coverage": delta.delta_known_cost_coverage,
        "raw_json": delta.raw_json,
    }


def _record_to_dict(record: RetroTimelineRecord) -> dict[str, Any]:
    return {
        "event": _event_to_dict(record.event),
        "before_window": _window_to_dict(record.before_window),
        "after_window": _window_to_dict(record.after_window),
        "delta": _delta_to_dict(record.delta),
    }


def render_retro_timeline_report_json(report: RetroTimelineReport) -> str:
    payload = {
        "metrics_path": str(report.metrics_path),
        "warehouse_path": str(report.warehouse_path),
        "cwd": str(report.cwd),
        "window_size": report.window_size,
        "event_count": len(report.events),
        "window_count": len(report.windows),
        "delta_count": len(report.deltas),
        "record_count": len(report.records),
        "events": [_event_to_dict(event) for event in report.events],
        "windows": [_window_to_dict(window) for window in report.windows],
        "deltas": [_delta_to_dict(delta) for delta in report.deltas],
        "records": [_record_to_dict(record) for record in report.records],
    }
    return json.dumps(payload, indent=2, sort_keys=True)
