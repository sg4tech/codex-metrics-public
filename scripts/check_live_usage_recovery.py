#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _load_cli_module():
    repo_src_path = Path(__file__).resolve().parents[1] / "src"
    if repo_src_path.exists():
        sys.path.insert(0, str(repo_src_path))

    from ai_agents_metrics import cli

    return cli


CLI = _load_cli_module()
SCRIPT_PATH = Path(__file__).resolve().parent / "update_codex_metrics.py"
DEFAULT_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
DEFAULT_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return int(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a live end-to-end smoke check that recovers usage from real Codex telemetry into temporary metrics files."
        )
    )
    parser.add_argument("--cwd", default=str(Path.cwd()), help="Workspace cwd used to resolve the Codex thread")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--logs-path", default=str(DEFAULT_LOGS_PATH))
    parser.add_argument("--pricing-path", default=str(CLI.PRICING_JSON_PATH))
    parser.add_argument("--thread-id", help="Optional explicit Codex thread id")
    return parser.parse_args()


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def find_live_event(
    *,
    cwd: Path,
    state_path: Path,
    logs_path: Path,
) -> tuple[str, Path, dict[str, object], str]:
    thread_id = CLI.find_codex_thread_id(state_path, cwd, None)
    if thread_id is None:
        raise RuntimeError(f"No Codex thread found for cwd: {cwd}")

    rollout_path = CLI.find_session_rollout_path(logs_path.parent / "sessions", thread_id)
    if rollout_path is None:
        raise RuntimeError(f"No rollout session found for thread: {thread_id}")

    model = CLI.resolve_thread_model_from_logs(logs_path, thread_id)
    if model is None:
        raise RuntimeError(f"Could not resolve model from logs for thread: {thread_id}")

    with rollout_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("type") != "event_msg":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            info = payload.get("info")
            if not isinstance(info, dict):
                continue
            last_usage = info.get("last_token_usage")
            if not isinstance(last_usage, dict):
                continue
            timestamp = record.get("timestamp")
            if not isinstance(timestamp, str):
                continue
            return thread_id, rollout_path, last_usage, timestamp

    raise RuntimeError(f"No token_count event found in rollout session: {rollout_path}")


def main() -> int:
    from ai_agents_metrics.domain import load_metrics

    args = parse_args()
    cwd = Path(args.cwd).resolve()
    state_path = Path(args.state_path).expanduser().resolve()
    logs_path = Path(args.logs_path).expanduser().resolve()
    pricing_path = Path(args.pricing_path).expanduser().resolve()
    explicit_thread_id = args.thread_id

    thread_id, rollout_path, last_usage, timestamp = find_live_event(
        cwd=cwd,
        state_path=state_path,
        logs_path=logs_path,
    )
    if explicit_thread_id is not None:
        thread_id = explicit_thread_id

    input_tokens = _as_int(last_usage.get("input_tokens"), 0)
    cached_input_tokens = _as_int(last_usage.get("cached_input_tokens"), 0)
    output_tokens = _as_int(last_usage.get("output_tokens"), 0)
    expected_tokens = _as_int(
        last_usage.get(
            "total_tokens",
            input_tokens + cached_input_tokens + output_tokens + _as_int(last_usage.get("reasoning_output_tokens"), 0),
        )
    )
    model = CLI.resolve_thread_model_from_logs(logs_path, thread_id)
    if model is None:
        raise RuntimeError(f"Could not resolve model from logs for thread: {thread_id}")
    pricing = CLI.load_pricing(pricing_path)
    expected_cost = CLI.compute_event_cost_usd(
        {
            "model": model,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
        },
        pricing,
    )

    with tempfile.TemporaryDirectory(prefix="codex-metrics-live-") as tmpdir:
        tmp_path = Path(tmpdir)
        metrics_path = tmp_path / "metrics" / "events.ndjson"
        report_path = tmp_path / "codex_metrics.md"
        missing_state = tmp_path / "missing_state.sqlite"
        missing_logs = tmp_path / "missing_logs.sqlite"

        init_result = run_cmd(
            "init",
            "--metrics-path",
            str(metrics_path),
            "--report-path",
            str(report_path),
        )
        if init_result.returncode != 0:
            raise RuntimeError(init_result.stderr or init_result.stdout)

        update_result = run_cmd(
            "update",
            "--task-id",
            "live-usage-e2e",
            "--title",
            "Live usage recovery smoke check",
            "--task-type",
            "product",
            "--status",
            "success",
            "--started-at",
            timestamp,
            "--finished-at",
            timestamp,
            "--metrics-path",
            str(metrics_path),
            "--report-path",
            str(report_path),
            "--codex-state-path",
            str(missing_state),
            "--codex-logs-path",
            str(missing_logs),
        )
        if update_result.returncode != 0:
            raise RuntimeError(update_result.stderr or update_result.stdout)

        sync_result = run_cmd(
            "sync-codex-usage",
            "--metrics-path",
            str(metrics_path),
            "--report-path",
            str(report_path),
            "--codex-state-path",
            str(state_path),
            "--codex-logs-path",
            str(logs_path),
            "--codex-thread-id",
            thread_id,
        )
        if sync_result.returncode != 0:
            raise RuntimeError(sync_result.stderr or sync_result.stdout)

        data = load_metrics(metrics_path)
        goal = next(goal for goal in data["goals"] if goal["goal_id"] == "live-usage-e2e")

    actual_tokens = goal["tokens_total"]
    actual_cost = goal["cost_usd"]
    if actual_tokens != expected_tokens:
        raise RuntimeError(
            f"Token mismatch: expected {expected_tokens}, got {actual_tokens}. Thread={thread_id}, timestamp={timestamp}"
        )
    if actual_cost != expected_cost:
        raise RuntimeError(
            f"Cost mismatch: expected {expected_cost}, got {actual_cost}. Thread={thread_id}, timestamp={timestamp}"
        )

    print("Live usage recovery smoke passed")
    print(f"Thread: {thread_id}")
    print(f"Rollout: {rollout_path}")
    print(f"Timestamp: {timestamp}")
    print(f"Model: {model}")
    print(f"Expected tokens: {expected_tokens}")
    print(f"Recovered tokens: {actual_tokens}")
    print(f"Expected cost_usd: {expected_cost}")
    print(f"Recovered cost_usd: {actual_cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
