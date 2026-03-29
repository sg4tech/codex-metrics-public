#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRICS_JSON_PATH = Path("metrics/codex_metrics.json")
REPORT_MD_PATH = Path("docs/codex-metrics.md")


ALLOWED_STATUSES = {"in_progress", "success", "fail"}
ALLOWED_FAILURE_REASONS = {
    "unclear_task",
    "missing_context",
    "validation_failed",
    "environment_issue",
    "model_mistake",
    "scope_too_large",
    "tooling_issue",
    "other",
}


@dataclass
class TaskRecord:
    task_id: str
    title: str
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
    cost_usd: float | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def default_metrics() -> dict[str, Any]:
    return {
        "summary": {
            "closed_tasks": 0,
            "successes": 0,
            "fails": 0,
            "total_attempts": 0,
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "success_rate": None,
            "attempts_per_success": None,
            "cost_per_success_usd": None,
            "cost_per_success_tokens": None,
        },
        "tasks": [],
    }


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_metrics()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "summary" not in data or "tasks" not in data:
        raise ValueError(f"Invalid metrics file format: {path}")
    return data


def save_metrics(path: Path, data: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def validate_status(status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {status}. Allowed: {sorted(ALLOWED_STATUSES)}")


def validate_failure_reason(reason: str | None) -> None:
    if reason is None:
        return
    if reason not in ALLOWED_FAILURE_REASONS:
        raise ValueError(
            f"Invalid failure reason: {reason}. Allowed: {sorted(ALLOWED_FAILURE_REASONS)}"
        )


def get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int | None:
    for idx, task in enumerate(tasks):
        if task.get("task_id") == task_id:
            return idx
    return None


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def format_num(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def recompute_summary(data: dict[str, Any]) -> None:
    tasks: list[dict[str, Any]] = data["tasks"]

    closed_tasks = [t for t in tasks if t["status"] in {"success", "fail"}]
    successes = [t for t in closed_tasks if t["status"] == "success"]
    fails = [t for t in closed_tasks if t["status"] == "fail"]

    total_attempts = sum(int(t.get("attempts") or 0) for t in closed_tasks)

    usd_values = [t["cost_usd"] for t in closed_tasks if t.get("cost_usd") is not None]
    total_cost_usd = float(sum(usd_values)) if usd_values else 0.0

    token_values = [int(t["tokens_total"]) for t in closed_tasks if t.get("tokens_total") is not None]
    total_tokens = sum(token_values) if token_values else 0

    success_rate = (len(successes) / len(closed_tasks)) if closed_tasks else None
    attempts_per_success = (total_attempts / len(successes)) if successes else None

    success_cost_values = [t["cost_usd"] for t in successes if t.get("cost_usd") is not None]
    cost_per_success_usd = (
        float(sum(success_cost_values)) / len(successes)
        if successes and len(success_cost_values) == len(successes)
        else None
    )

    success_token_values = [int(t["tokens_total"]) for t in successes if t.get("tokens_total") is not None]
    cost_per_success_tokens = (
        sum(success_token_values) / len(successes)
        if successes and len(success_token_values) == len(successes)
        else None
    )

    data["summary"] = {
        "closed_tasks": len(closed_tasks),
        "successes": len(successes),
        "fails": len(fails),
        "total_attempts": total_attempts,
        "total_cost_usd": round(total_cost_usd, 6),
        "total_tokens": total_tokens,
        "success_rate": success_rate,
        "attempts_per_success": attempts_per_success,
        "cost_per_success_usd": round(cost_per_success_usd, 6) if cost_per_success_usd is not None else None,
        "cost_per_success_tokens": cost_per_success_tokens,
    }


def generate_report_md(data: dict[str, Any]) -> str:
    summary = data["summary"]
    tasks: list[dict[str, Any]] = data["tasks"]

    lines: list[str] = [
        "# Codex Metrics",
        "",
        "## Current summary",
        "",
        f"- Closed tasks: {summary['closed_tasks']}",
        f"- Successes: {summary['successes']}",
        f"- Fails: {summary['fails']}",
        f"- Total attempts: {summary['total_attempts']}",
        f"- Total cost (USD): {format_num(summary['total_cost_usd'])}",
        f"- Total tokens: {summary['total_tokens']}",
        f"- Success Rate: {format_pct(summary['success_rate'])}",
        f"- Attempts per Success: {format_num(summary['attempts_per_success'])}",
        f"- Cost per Success (USD): {format_num(summary['cost_per_success_usd'])}",
        f"- Cost per Success (Tokens): {format_num(summary['cost_per_success_tokens'])}",
        "",
        "## Task log",
        "",
    ]

    if not tasks:
        lines.append("_No tasks recorded yet._")
        lines.append("")
        return "\n".join(lines)

    for task in sorted(tasks, key=lambda x: x.get("started_at") or "", reverse=True):
        lines.extend(
            [
                f"### {task['task_id']} — {task['title']}",
                f"- Status: {task['status']}",
                f"- Attempts: {task['attempts']}",
                f"- Started at: {task['started_at'] or 'n/a'}",
                f"- Finished at: {task['finished_at'] or 'n/a'}",
                f"- Cost (USD): {format_num(task.get('cost_usd'))}",
                f"- Tokens: {format_num(task.get('tokens_total'))}",
                f"- Failure reason: {task.get('failure_reason') or 'n/a'}",
                f"- Notes: {task.get('notes') or 'n/a'}",
                "",
            ]
        )

    return "\n".join(lines)


def save_report(path: Path, data: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    report = generate_report_md(data)
    path.write_text(report, encoding="utf-8")


def init_files(metrics_path: Path, report_path: Path) -> None:
    data = default_metrics()
    save_metrics(metrics_path, data)
    save_report(report_path, data)


def upsert_task(
    data: dict[str, Any],
    task_id: str,
    title: str | None,
    status: str | None,
    attempts_delta: int | None,
    attempts_abs: int | None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    failure_reason: str | None,
    notes: str | None,
    started_at: str | None,
    finished_at: str | None,
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = data["tasks"]
    task_index = get_task_index(tasks, task_id)

    if task_index is None:
        if title is None:
            raise ValueError("title is required when creating a new task")
        task = TaskRecord(
            task_id=task_id,
            title=title,
            status="in_progress",
            attempts=0,
            started_at=started_at or now_utc_iso(),
            finished_at=None,
            cost_usd=None,
            tokens_total=None,
            failure_reason=None,
            notes=None,
        )
        tasks.append(asdict(task))
        task_index = len(tasks) - 1

    task = tasks[task_index]

    if title is not None:
        task["title"] = title
    if status is not None:
        validate_status(status)
        task["status"] = status
    if attempts_abs is not None:
        if attempts_abs < 0:
            raise ValueError("attempts cannot be negative")
        task["attempts"] = attempts_abs
    if attempts_delta is not None:
        if attempts_delta < 0:
            raise ValueError("attempts_delta cannot be negative")
        task["attempts"] = int(task.get("attempts") or 0) + attempts_delta

    if cost_usd_set is not None:
        task["cost_usd"] = cost_usd_set
    elif cost_usd_add is not None:
        current = task.get("cost_usd") or 0.0
        task["cost_usd"] = round(float(current) + cost_usd_add, 6)

    if tokens_set is not None:
        task["tokens_total"] = tokens_set
    elif tokens_add is not None:
        current = int(task.get("tokens_total") or 0)
        task["tokens_total"] = current + tokens_add

    if failure_reason is not None:
        validate_failure_reason(failure_reason)
        task["failure_reason"] = failure_reason

    if notes is not None:
        task["notes"] = notes

    if started_at is not None:
        task["started_at"] = started_at

    if finished_at is not None:
        task["finished_at"] = finished_at

    if task["status"] in {"success", "fail"} and not task.get("finished_at"):
        task["finished_at"] = now_utc_iso()

    return task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update Codex task metrics")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize metrics files")
    init_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    init_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))

    update_parser = subparsers.add_parser("update", help="Create or update a task")
    update_parser.add_argument("--task-id", required=True)
    update_parser.add_argument("--title")
    update_parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES))
    update_parser.add_argument("--attempts-delta", type=int)
    update_parser.add_argument("--attempts", type=int)
    update_parser.add_argument("--cost-usd-add", type=float)
    update_parser.add_argument("--cost-usd", type=float)
    update_parser.add_argument("--tokens-add", type=int)
    update_parser.add_argument("--tokens", type=int)
    update_parser.add_argument("--failure-reason", choices=sorted(ALLOWED_FAILURE_REASONS))
    update_parser.add_argument("--notes")
    update_parser.add_argument("--started-at")
    update_parser.add_argument("--finished-at")
    update_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))
    update_parser.add_argument("--report-path", default=str(REPORT_MD_PATH))

    show_parser = subparsers.add_parser("show", help="Print current summary")
    show_parser.add_argument("--metrics-path", default=str(METRICS_JSON_PATH))

    return parser


def print_summary(data: dict[str, Any]) -> None:
    summary = data["summary"]
    print("Codex Metrics Summary")
    print(f"Closed tasks: {summary['closed_tasks']}")
    print(f"Successes: {summary['successes']}")
    print(f"Fails: {summary['fails']}")
    print(f"Total attempts: {summary['total_attempts']}")
    print(f"Total cost (USD): {format_num(summary['total_cost_usd'])}")
    print(f"Total tokens: {summary['total_tokens']}")
    print(f"Success Rate: {format_pct(summary['success_rate'])}")
    print(f"Attempts per Success: {format_num(summary['attempts_per_success'])}")
    print(f"Cost per Success (USD): {format_num(summary['cost_per_success_usd'])}")
    print(f"Cost per Success (Tokens): {format_num(summary['cost_per_success_tokens'])}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        init_files(metrics_path, report_path)
        print(f"Initialized {metrics_path} and {report_path}")
        return 0

    if args.command == "show":
        metrics_path = Path(args.metrics_path)
        data = load_metrics(metrics_path)
        recompute_summary(data)
        print_summary(data)
        return 0

    if args.command == "update":
        metrics_path = Path(args.metrics_path)
        report_path = Path(args.report_path)
        data = load_metrics(metrics_path)

        task = upsert_task(
            data=data,
            task_id=args.task_id,
            title=args.title,
            status=args.status,
            attempts_delta=args.attempts_delta,
            attempts_abs=args.attempts,
            cost_usd_add=args.cost_usd_add,
            cost_usd_set=args.cost_usd,
            tokens_add=args.tokens_add,
            tokens_set=args.tokens,
            failure_reason=args.failure_reason,
            notes=args.notes,
            started_at=args.started_at,
            finished_at=args.finished_at,
        )

        recompute_summary(data)
        save_metrics(metrics_path, data)
        save_report(report_path, data)

        print(f"Updated task {task['task_id']}")
        print(f"Status: {task['status']}")
        print(f"Attempts: {task['attempts']}")
        print_summary(data)
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())