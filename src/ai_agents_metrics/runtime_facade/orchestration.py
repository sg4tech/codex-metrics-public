"""Path constants, history-pipeline wrappers, workflow helpers, init/bootstrap/save_report."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.bootstrap import (
    BootstrapCallbacks,
    BootstrapPaths,
)
from ai_agents_metrics.bootstrap import (
    bootstrap_project as run_bootstrap_project,
)
from ai_agents_metrics.domain import (
    create_goal_record,
    default_metrics,
    goal_to_dict,
    load_metrics,
    next_goal_id,
    now_utc_iso,
    recompute_summary,
    validate_goal_record,
)
from ai_agents_metrics.git_state import (
    ActiveTaskResolution,
    detect_started_work,
)
from ai_agents_metrics.history.classify import (
    classify_codex_history as run_classify_codex_history,
)
from ai_agents_metrics.history.derive import (
    derive_codex_history as run_derive_codex_history,
)
from ai_agents_metrics.history.ingest import (
    default_raw_warehouse_path,
)
from ai_agents_metrics.history.ingest import (
    ingest_codex_history as run_ingest_codex_history,
)
from ai_agents_metrics.history.normalize import (
    normalize_codex_history as run_normalize_codex_history,
)
from ai_agents_metrics.public_boundary import (
    verify_public_boundary as run_verify_public_boundary,
)
from ai_agents_metrics.reporting import generate_report_md
from ai_agents_metrics.storage import atomic_write_text, ensure_parent_dir
from ai_agents_metrics.workflow_fsm import (
    WorkflowEvent,
    WorkflowResolution,
    resolve_workflow_transition,
)

if TYPE_CHECKING:
    from ai_agents_metrics.history.classify import ClassifySummary
    from ai_agents_metrics.history.derive import DeriveSummary
    from ai_agents_metrics.history.ingest import IngestSummary
    from ai_agents_metrics.history.normalize import NormalizeSummary
    from ai_agents_metrics.public_boundary import PublicBoundaryReport


EVENTS_NDJSON_PATH = Path("metrics/events.ndjson")
METRICS_JSON_PATH = EVENTS_NDJSON_PATH
REPORT_MD_PATH = Path("docs/ai-agents-metrics.md")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
CLAUDE_ROOT = Path.home() / ".claude"
RAW_WAREHOUSE_PATH = default_raw_warehouse_path(METRICS_JSON_PATH)


def ingest_codex_history(source_root: Path, warehouse_path: Path, source: str = "codex") -> IngestSummary:
    return run_ingest_codex_history(source_root=source_root, warehouse_path=warehouse_path, source=source)


def normalize_codex_history(warehouse_path: Path) -> NormalizeSummary:
    return run_normalize_codex_history(warehouse_path=warehouse_path)


def derive_codex_history(warehouse_path: Path) -> DeriveSummary:
    return run_derive_codex_history(warehouse_path=warehouse_path)


def classify_codex_history(warehouse_path: Path) -> ClassifySummary:
    return run_classify_codex_history(warehouse_path=warehouse_path)


def verify_public_boundary(*, repo_root: Path, rules_path: Path) -> PublicBoundaryReport:
    return run_verify_public_boundary(repo_root=repo_root, rules_path=rules_path)


def get_active_goals(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [goal for goal in data["goals"] if goal.get("status") == "in_progress"]


def resolve_workflow_resolution(data: dict[str, Any], cwd: Path, event: WorkflowEvent) -> WorkflowResolution:
    report = detect_started_work(cwd)
    return resolve_workflow_transition(
        active_goal_count=len(get_active_goals(data)),
        started_work_detected=report.started_work_detected if report.git_available else None,
        git_available=report.git_available,
        event=event,
    )


def ensure_active_task(data: dict[str, Any], cwd: Path) -> ActiveTaskResolution:
    report = detect_started_work(cwd)
    resolution = resolve_workflow_resolution(data, cwd, WorkflowEvent.ENSURE_ACTIVE_TASK)
    decision = resolution.decision
    active_goals = get_active_goals(data)
    if active_goals and decision.action == "no_op":
        active_ids = ", ".join(goal["goal_id"] for goal in active_goals)
        active_goal = active_goals[0]
        return ActiveTaskResolution(
            status="existing",
            goal_id=active_goal["goal_id"] if len(active_goals) == 1 else None,
            message=f"Active goal already exists: {active_ids}",
        )
    if decision.action == "no_op":
        return ActiveTaskResolution(
            status="not_needed",
            goal_id=None,
            message=decision.message,
            started_work_report=report,
        )

    tasks: list[dict[str, Any]] = data["goals"]
    new_task_id = next_goal_id(tasks)
    new_goal = create_goal_record(
        tasks=tasks,
        task_id=new_task_id,
        title="Recover active task for in-progress repository work",
        task_type="meta",
        linked_task_id=None,
        started_at=now_utc_iso(),
        model=None,
    )
    new_goal.notes = (
        "Auto-recovered because repository work was detected before task bookkeeping started. "
        f"Detected changes: {', '.join(report.changed_paths[:5]) if report.changed_paths else 'none'}"
    )
    goal_dict = goal_to_dict(new_goal)
    tasks[-1] = goal_dict
    validate_goal_record(goal_dict)
    return ActiveTaskResolution(
        status="created",
        goal_id=new_task_id,
        message=f"Created recovery goal {new_task_id}",
        started_work_report=report,
    )


def save_report(path: Path, data: dict[str, Any]) -> None:
    report = generate_report_md(data)
    atomic_write_text(path, report)


def init_files(metrics_path: Path, report_path: Path | None, force: bool = False) -> None:
    if not force:
        existing_paths = [path for path in (metrics_path, report_path) if path is not None and path.exists()]
        if existing_paths:
            joined_paths = ", ".join(str(path) for path in existing_paths)
            raise ValueError(
                f"Metrics files already exist: {joined_paths}. Use --force to overwrite."
            )
    ensure_parent_dir(metrics_path)
    metrics_path.write_text("", encoding="utf-8")
    if report_path is not None:
        data = default_metrics()
        recompute_summary(data)
        save_report(report_path, data)


def bootstrap_project(
    *,
    target_dir: Path,
    metrics_path: Path,
    report_path: Path | None,
    policy_path: Path,
    command_path: Path,
    agents_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    del target_dir
    result = run_bootstrap_project(
        paths=BootstrapPaths(
            metrics_path=metrics_path,
            report_path=report_path,
            policy_path=policy_path,
            command_path=command_path,
            agents_path=agents_path,
        ),
        force=force,
        dry_run=dry_run,
        callbacks=BootstrapCallbacks(
            load_metrics=load_metrics,
            default_metrics=default_metrics,
            save_report=save_report,
        ),
    )
    return result.messages
