from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

from ai_agents_metrics.bootstrap import (
    BootstrapCallbacks,
    BootstrapPaths,
)
from ai_agents_metrics.bootstrap import (
    bootstrap_project as run_bootstrap_project,
)
from ai_agents_metrics.cost_audit import (
    CostAuditContext,
    CostAuditReport,
    render_cost_audit_report_json,
)
from ai_agents_metrics.cost_audit import (
    audit_cost_coverage as _run_audit_cost_coverage,
)
from ai_agents_metrics.domain import (
    GoalRecord,
    apply_goal_updates,
    build_merged_notes,
    choose_earliest_timestamp,
    choose_latest_timestamp,
    combine_optional_cost,
    combine_optional_tokens,
    create_goal_record,
    default_metrics,
    finalize_goal_update,
    get_task_index,
    goal_from_dict,
    goal_to_dict,
    load_metrics,
    next_goal_id,
    now_utc_iso,
    recompute_summary,
    resolve_linked_task_reference,
    round_usd,
    sync_goal_attempt_entries,
    validate_entry_record,
    validate_goal_record,
    validate_goal_supersession_graph,
    validate_non_negative_int,
)
from ai_agents_metrics.git_state import (
    StartedWorkReport,
    detect_started_work,
)
from ai_agents_metrics.history.audit import (
    audit_history,
    render_audit_report,
    render_audit_report_json,
)
from ai_agents_metrics.history.classify import (
    ClassifySummary,
    render_classify_summary_json,
)
from ai_agents_metrics.history.classify import (
    classify_codex_history as run_classify_codex_history,
)
from ai_agents_metrics.history.compare import (
    compare_metrics_to_history,
    read_history_signals,
    render_history_compare_report,
    render_history_compare_report_json,
)
from ai_agents_metrics.history.derive import (
    DeriveSummary,
    render_derive_summary_json,
)
from ai_agents_metrics.history.derive import (
    derive_codex_history as run_derive_codex_history,
)
from ai_agents_metrics.history.ingest import (
    IngestSummary,
    default_raw_warehouse_path,
    render_ingest_summary_json,
)
from ai_agents_metrics.history.ingest import (
    ingest_codex_history as run_ingest_codex_history,
)
from ai_agents_metrics.history.normalize import (
    NormalizeSummary,
    render_normalize_summary_json,
)
from ai_agents_metrics.history.normalize import (
    normalize_codex_history as run_normalize_codex_history,
)
from ai_agents_metrics.pricing_runtime import (
    load_effective_pricing,
    resolve_effective_pricing_path,
)
from ai_agents_metrics.public_boundary import (
    PublicBoundaryReport,
)
from ai_agents_metrics.public_boundary import (
    verify_public_boundary as run_verify_public_boundary,
)
from ai_agents_metrics.reporting import (
    generate_report_md,
    print_summary,
    render_summary_json,
)
from ai_agents_metrics.retro_timeline import (
    derive_retro_timeline,
    render_retro_timeline_report,
    render_retro_timeline_report_json,
)
from ai_agents_metrics.storage import (
    atomic_write_text,
    ensure_parent_dir,
    metrics_mutation_lock,
)
from ai_agents_metrics.usage_backends import (
    ClaudeUsageBackend,
    UsageBackend,
    select_usage_backend,
)
from ai_agents_metrics.usage_backends import (
    resolve_usage_window as resolve_backend_usage_window,
)
from ai_agents_metrics.usage_resolution import (
    PRICING_JSON_PATH,
    compute_event_cost_usd,
    find_usage_thread_id,
    load_pricing,
    parse_usage_event,
    resolve_codex_session_usage_window,
    resolve_codex_usage_window,
    resolve_pricing_model_alias,
    resolve_pricing_path,
    resolve_usage_session_window,
)
from ai_agents_metrics.workflow_fsm import (
    WorkflowEvent,
    WorkflowResolution,
    resolve_workflow_transition,
)

EVENTS_NDJSON_PATH = Path("metrics/events.ndjson")
METRICS_JSON_PATH = EVENTS_NDJSON_PATH
REPORT_MD_PATH = Path("docs/ai-agents-metrics.md")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
CLAUDE_ROOT = Path.home() / ".claude"
RAW_WAREHOUSE_PATH = default_raw_warehouse_path(METRICS_JSON_PATH)

__all__ = [
    "ActiveTaskResolution",
    "CLAUDE_ROOT",
    "CODEX_LOGS_PATH",
    "CODEX_STATE_PATH",
    "EVENTS_NDJSON_PATH",
    "GoalUsageResolution",
    "METRICS_JSON_PATH",
    "PRICING_JSON_PATH",
    "RAW_WAREHOUSE_PATH",
    "REPORT_MD_PATH",
    "audit_cost_coverage",
    "audit_history",
    "bootstrap_project",
    "classify_codex_history",
    "compare_metrics_to_history",
    "compute_event_cost_usd",
    "derive_codex_history",
    "derive_retro_timeline",
    "detect_started_work",
    "ensure_active_task",
    "find_usage_thread_id",
    "get_active_goals",
    "ingest_codex_history",
    "init_files",
    "load_effective_pricing",
    "load_metrics",
    "load_pricing",
    "merge_tasks",
    "metrics_mutation_lock",
    "normalize_codex_history",
    "parse_usage_event",
    "print_summary",
    "read_history_signals",
    "recompute_summary",
    "render_audit_report",
    "render_audit_report_json",
    "render_classify_summary_json",
    "render_cost_audit_report_json",
    "render_derive_summary_json",
    "render_history_compare_report",
    "render_history_compare_report_json",
    "render_ingest_summary_json",
    "render_normalize_summary_json",
    "render_retro_timeline_report",
    "render_retro_timeline_report_json",
    "render_summary_json",
    "resolve_codex_session_usage_window",
    "resolve_codex_usage_window",
    "resolve_effective_pricing_path",
    "resolve_goal_usage_updates",
    "resolve_pricing_model_alias",
    "resolve_pricing_path",
    "resolve_usage_session_window",
    "resolve_workflow_resolution",
    "save_report",
    "sync_codex_usage",
    "sync_usage",
    "upsert_task",
    "verify_public_boundary",
]


@dataclass(frozen=True)
class ActiveTaskResolution:
    status: str
    goal_id: str | None
    message: str
    started_work_report: StartedWorkReport | None = None


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


def resolve_usage_costs(
    *,
    pricing_path: Path,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    explicit_cost_fields_used: bool,
    explicit_token_fields_used: bool,
) -> tuple[float | None, int | None, int | None, int | None, int | None, str | None]:
    usage_fields_used = any(value is not None for value in (input_tokens, cached_input_tokens, output_tokens))
    if model is None and not usage_fields_used:
        return None, None, None, None, None, None
    if model is None:
        raise ValueError("model is required when usage token flags are provided")
    if not usage_fields_used:
        raise ValueError("At least one usage token field is required when model is provided")
    if explicit_cost_fields_used or explicit_token_fields_used:
        raise ValueError("model-based usage pricing cannot be combined with explicit cost/token flags")

    input_tokens_value = input_tokens or 0
    cached_input_tokens_value = cached_input_tokens or 0
    output_tokens_value = output_tokens or 0
    validate_non_negative_int(input_tokens_value, "input_tokens")
    validate_non_negative_int(cached_input_tokens_value, "cached_input_tokens")
    validate_non_negative_int(output_tokens_value, "output_tokens")

    pricing = load_pricing(pricing_path)
    pricing_model = resolve_pricing_model_alias(model, pricing)
    if pricing_model is None:
        raise ValueError(f"Unknown model: {model!r} — not found in pricing file {pricing_path}")
    model_pricing = pricing[pricing_model]
    cached_rate = model_pricing["cached_input_per_million_usd"]
    if cached_input_tokens_value > 0 and cached_rate is None:
        raise ValueError(f"Model {model} does not support cached input pricing")

    input_cost = Decimal(str(model_pricing["input_per_million_usd"])) * Decimal(input_tokens_value) / Decimal(1_000_000)
    cached_input_cost = Decimal("0")
    if cached_rate is not None:
        cached_input_cost = Decimal(str(cached_rate)) * Decimal(cached_input_tokens_value) / Decimal(1_000_000)
    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(output_tokens_value) / Decimal(1_000_000)
    total_cost = round_usd(input_cost + cached_input_cost + output_cost)
    total_tokens = input_tokens_value + cached_input_tokens_value + output_tokens_value
    return total_cost, total_tokens, input_tokens_value, cached_input_tokens_value, output_tokens_value, model


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


class GoalUsageResolution(NamedTuple):
    """Named return type for :func:`resolve_goal_usage_updates`.

    Subclassing ``NamedTuple`` preserves the existing positional tuple contract
    (e.g. ``*_, detected = resolve_goal_usage_updates(...)``) while giving
    internal callers attribute access so mypy flags field-order mistakes.
    """

    usage_cost_usd: float | None
    usage_total_tokens: int | None
    usage_input_tokens: int | None
    usage_cached_input_tokens: int | None
    usage_output_tokens: int | None
    usage_model: str | None
    auto_cost_usd: float | None
    auto_total_tokens: int | None
    auto_input_tokens: int | None
    auto_cached_input_tokens: int | None
    auto_output_tokens: int | None
    auto_model: str | None
    detected_agent_name: str | None


# Wide kwargs surface reflects the CLI update contract (manual / usage-driven
# / auto-recovered sources kept distinct for precedence). Grouping into
# sub-dataclasses is tracked as a follow-up once precedence rules stabilise.
def resolve_goal_usage_updates(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    task: GoalRecord,
    usage_backend: UsageBackend | None = None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    started_at: str | None,
    finished_at: str | None,
    claude_root: Path = CLAUDE_ROOT,
) -> GoalUsageResolution:
    explicit_cost_fields_used = cost_usd_add is not None or cost_usd_set is not None
    explicit_token_fields_used = tokens_add is not None or tokens_set is not None

    effective_agent_name = task.agent_name
    detected_agent_name: str | None = None

    if usage_backend is not None:
        resolved_usage_backend: UsageBackend = usage_backend
        usage_state_path = codex_state_path
    elif effective_agent_name == "claude":
        resolved_usage_backend = ClaudeUsageBackend()
        usage_state_path = claude_root
    else:
        resolved_usage_backend = select_usage_backend(codex_state_path, cwd, codex_thread_id)
        usage_state_path = codex_state_path

    usage_cost_usd, usage_total_tokens, usage_input_tokens, usage_cached_input_tokens, usage_output_tokens, usage_model = resolve_usage_costs(
        pricing_path=pricing_path,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        explicit_cost_fields_used=explicit_cost_fields_used,
        explicit_token_fields_used=explicit_token_fields_used,
    )

    auto_cost_usd, auto_total_tokens, auto_input_tokens, auto_cached_input_tokens, auto_output_tokens, auto_model = (
        None,
        None,
        None,
        None,
        None,
        None,
    )
    if usage_cost_usd is None and usage_total_tokens is None:
        task_started_at = task.started_at.isoformat() if task.started_at is not None else None
        task_finished_at = task.finished_at.isoformat() if task.finished_at is not None else None
        window = resolve_backend_usage_window(
            resolved_usage_backend,
            state_path=usage_state_path,
            logs_path=codex_logs_path,
            cwd=cwd,
            started_at=started_at if started_at is not None else task_started_at,
            finished_at=finished_at if finished_at is not None else task_finished_at,
            pricing_path=pricing_path,
            thread_id=codex_thread_id,
        )
        auto_cost_usd = window.cost_usd
        auto_total_tokens = window.total_tokens
        auto_input_tokens = window.input_tokens
        auto_cached_input_tokens = window.cached_input_tokens
        auto_output_tokens = window.output_tokens
        auto_model = window.model_name

        if (
            auto_cost_usd is None
            and auto_total_tokens is None
            and effective_agent_name is None
            and usage_backend is None
        ):
            claude_window = resolve_backend_usage_window(
                ClaudeUsageBackend(),
                state_path=claude_root,
                logs_path=codex_logs_path,
                cwd=cwd,
                started_at=started_at if started_at is not None else task_started_at,
                finished_at=finished_at if finished_at is not None else task_finished_at,
                pricing_path=pricing_path,
                thread_id=None,
            )
            if claude_window.cost_usd is not None or claude_window.total_tokens is not None:
                window = claude_window
                auto_cost_usd = window.cost_usd
                auto_total_tokens = window.total_tokens
                auto_input_tokens = window.input_tokens
                auto_cached_input_tokens = window.cached_input_tokens
                auto_output_tokens = window.output_tokens
                auto_model = window.model_name

        if auto_cost_usd is not None or auto_total_tokens is not None:
            if task.agent_name is None:
                detected_agent_name = window.backend_name

    return GoalUsageResolution(
        usage_cost_usd=usage_cost_usd,
        usage_total_tokens=usage_total_tokens,
        usage_input_tokens=usage_input_tokens,
        usage_cached_input_tokens=usage_cached_input_tokens,
        usage_output_tokens=usage_output_tokens,
        usage_model=usage_model,
        auto_cost_usd=auto_cost_usd,
        auto_total_tokens=auto_total_tokens,
        auto_input_tokens=auto_input_tokens,
        auto_cached_input_tokens=auto_cached_input_tokens,
        auto_output_tokens=auto_output_tokens,
        auto_model=auto_model,
        detected_agent_name=detected_agent_name,
    )


# upsert_task is the central CLI-surface mutator; its kwargs mirror the
# `update`/`start-task`/`finish-task` argparse flags. See apply_goal_updates
# for the matching precedent and follow-up plan.
def upsert_task(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    data: dict[str, Any],
    task_id: str | None,
    title: str | None,
    task_type: str | None,
    continuation_of: str | None,
    supersedes_task_id: str | None,
    status: str | None,
    attempts_delta: int | None,
    attempts_abs: int | None,
    cost_usd_add: float | None,
    cost_usd_set: float | None,
    tokens_add: int | None,
    tokens_set: int | None,
    failure_reason: str | None,
    result_fit: str | None,
    notes: str | None,
    started_at: str | None,
    finished_at: str | None,
    model: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    claude_root: Path = CLAUDE_ROOT,
    usage_backend: UsageBackend | None = None,
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = data["goals"]
    entries: list[dict[str, Any]] = data["entries"]
    creating_new_task = task_id is None
    if task_id is not None:
        creating_new_task = get_task_index(tasks, task_id) is None
    elif title is None and task_type is None:
        raise ValueError("task_id is required when updating an existing task")
    if task_id is None:
        task_id = next_goal_id(tasks)

    task_index = get_task_index(tasks, task_id)
    linked_task_id = resolve_linked_task_reference(
        tasks=tasks,
        continuation_of=continuation_of,
        supersedes_task_id=supersedes_task_id,
        creating_new_task=creating_new_task,
    )

    if task_index is None:
        create_goal_record(
            tasks=tasks,
            task_id=task_id,
            title=title,
            task_type=task_type,
            linked_task_id=linked_task_id,
            started_at=started_at,
            model=model,
        )
        task_index = len(tasks) - 1

    task = goal_from_dict(tasks[task_index])
    resolution = resolve_goal_usage_updates(
        task=task,
        usage_backend=usage_backend,
        cost_usd_add=cost_usd_add,
        cost_usd_set=cost_usd_set,
        tokens_add=tokens_add,
        tokens_set=tokens_set,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        codex_thread_id=codex_thread_id,
        cwd=cwd,
        started_at=started_at,
        finished_at=finished_at,
        claude_root=claude_root,
    )
    apply_goal_updates(
        entries=entries,
        task=task,
        title=title,
        task_type=task_type,
        status=status,
        attempts_delta=attempts_delta,
        attempts_abs=attempts_abs,
        cost_usd_add=cost_usd_add,
        cost_usd_set=cost_usd_set,
        input_tokens_add=None,
        cached_input_tokens_add=None,
        output_tokens_add=None,
        tokens_add=tokens_add,
        tokens_set=tokens_set,
        usage_cost_usd=resolution.usage_cost_usd,
        usage_input_tokens=resolution.usage_input_tokens,
        usage_cached_input_tokens=resolution.usage_cached_input_tokens,
        usage_output_tokens=resolution.usage_output_tokens,
        usage_total_tokens=resolution.usage_total_tokens,
        auto_cost_usd=resolution.auto_cost_usd,
        auto_input_tokens=resolution.auto_input_tokens,
        auto_cached_input_tokens=resolution.auto_cached_input_tokens,
        auto_output_tokens=resolution.auto_output_tokens,
        auto_total_tokens=resolution.auto_total_tokens,
        model=model,
        usage_model=resolution.usage_model,
        auto_model=resolution.auto_model,
        failure_reason=failure_reason,
        notes=notes,
        agent_name=resolution.detected_agent_name,
        started_at=started_at,
        finished_at=finished_at,
        result_fit=result_fit,
    )
    finalize_goal_update(task)
    task_dict = goal_to_dict(task)
    tasks[task_index] = task_dict
    return task_dict


def _resolve_sync_usage_window(
    task: dict[str, Any],
    *,
    cwd: Path,
    pricing_path: Path,
    usage_state_path: Path,
    usage_logs_path: Path,
    usage_thread_id: str | None,
    usage_backend: UsageBackend | None,
    claude_root: Path,
) -> tuple[Any, str | None]:
    """Resolve the usage window for one task; return (window, detected_agent_name)."""
    task_agent_name = task.get("agent_name")
    detected_agent_name: str | None = None
    if usage_backend is not None:
        resolved_backend: UsageBackend = usage_backend
        effective_state_path = usage_state_path
    elif task_agent_name == "claude":
        resolved_backend = ClaudeUsageBackend()
        effective_state_path = claude_root
    else:
        resolved_backend = select_usage_backend(usage_state_path, cwd, usage_thread_id)
        effective_state_path = usage_state_path
    window = resolve_backend_usage_window(
        resolved_backend,
        state_path=effective_state_path,
        logs_path=usage_logs_path,
        cwd=cwd,
        started_at=task.get("started_at"),
        finished_at=task.get("finished_at"),
        pricing_path=pricing_path,
        thread_id=usage_thread_id,
    )
    if (
        window.cost_usd is None
        and window.total_tokens is None
        and task_agent_name is None
        and usage_backend is None
    ):
        claude_window = resolve_backend_usage_window(
            ClaudeUsageBackend(),
            state_path=claude_root,
            logs_path=usage_logs_path,
            cwd=cwd,
            started_at=task.get("started_at"),
            finished_at=task.get("finished_at"),
            pricing_path=pricing_path,
            thread_id=None,
        )
        if claude_window.cost_usd is not None or claude_window.total_tokens is not None:
            window = claude_window
            detected_agent_name = claude_window.backend_name
    return window, detected_agent_name


def _apply_auto_usage_updates(
    task: dict[str, Any], window: Any, detected_agent_name: str | None
) -> bool:
    """Copy resolved window fields onto *task*; return True if anything changed."""
    auto_fields: list[tuple[str, Any]] = [
        ("cost_usd", window.cost_usd),
        ("input_tokens", window.input_tokens),
        ("cached_input_tokens", window.cached_input_tokens),
        ("output_tokens", window.output_tokens),
        ("tokens_total", window.total_tokens),
        ("model", window.model_name),
    ]
    if all(value is None for _, value in auto_fields):
        return False
    changed = False
    for field_name, value in auto_fields:
        if value is not None and task.get(field_name) != value:
            task[field_name] = value
            changed = True
    if detected_agent_name is not None and task.get("agent_name") is None:
        task["agent_name"] = detected_agent_name
        changed = True
    return changed


def sync_usage(
    data: dict[str, Any],
    *,
    cwd: Path,
    pricing_path: Path,
    usage_state_path: Path,
    usage_logs_path: Path,
    usage_thread_id: str | None,
    usage_backend: UsageBackend | None = None,
    claude_root: Path = CLAUDE_ROOT,
) -> int:
    updated_tasks = 0
    tasks: list[dict[str, Any]] = data["goals"]
    for task in tasks:
        previous_task = dict(task)
        window, detected_agent_name = _resolve_sync_usage_window(
            task,
            cwd=cwd,
            pricing_path=pricing_path,
            usage_state_path=usage_state_path,
            usage_logs_path=usage_logs_path,
            usage_thread_id=usage_thread_id,
            usage_backend=usage_backend,
            claude_root=claude_root,
        )
        if not _apply_auto_usage_updates(task, window, detected_agent_name):
            continue
        validate_goal_record(task)
        sync_goal_attempt_entries(data, task, previous_task)
        updated_tasks += 1
    return updated_tasks


def sync_codex_usage(
    data: dict[str, Any],
    *,
    cwd: Path,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    usage_backend: UsageBackend | None = None,
) -> int:
    return sync_usage(
        data=data,
        cwd=cwd,
        pricing_path=pricing_path,
        usage_state_path=codex_state_path,
        usage_logs_path=codex_logs_path,
        usage_thread_id=codex_thread_id,
        usage_backend=usage_backend,
    )


def audit_cost_coverage(
    data: dict[str, Any],
    *,
    pricing_path: Path,
    codex_state_path: Path,
    codex_logs_path: Path,
    codex_thread_id: str | None,
    cwd: Path,
    claude_root: Path = CLAUDE_ROOT,
) -> CostAuditReport:
    def resolve_cost_audit_usage_window(
        *,
        state_path: Path,
        logs_path: Path,
        cwd: Path,
        started_at: str | None,
        finished_at: str | None,
        pricing_path: Path,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> tuple[float | None, int | None]:
        if agent_name == "claude":
            backend: UsageBackend = ClaudeUsageBackend()
        else:
            backend = select_usage_backend(state_path, cwd, thread_id)
        window = resolve_backend_usage_window(
            backend,
            state_path=state_path,
            logs_path=logs_path,
            cwd=cwd,
            started_at=started_at,
            finished_at=finished_at,
            pricing_path=pricing_path,
            thread_id=thread_id,
        )
        return window.cost_usd, window.total_tokens

    return _run_audit_cost_coverage(
        data,
        context=CostAuditContext(
            pricing_path=pricing_path,
            codex_state_path=codex_state_path,
            codex_logs_path=codex_logs_path,
            claude_root=claude_root,
            cwd=cwd,
            codex_thread_id=codex_thread_id,
            find_thread_id=find_usage_thread_id,
            resolve_usage_window=resolve_cost_audit_usage_window,
        ),
    )


def _validate_merge_preconditions(
    tasks: list[dict[str, Any]],
    keep_task_id: str,
    drop_task_id: str,
) -> tuple[int, int, dict[str, Any], dict[str, Any]]:
    if keep_task_id == drop_task_id:
        raise ValueError("keep_task_id and drop_task_id must be different")
    keep_index = get_task_index(tasks, keep_task_id)
    drop_index = get_task_index(tasks, drop_task_id)
    if keep_index is None:
        raise ValueError(f"Goal not found: {keep_task_id}")
    if drop_index is None:
        raise ValueError(f"Goal not found: {drop_task_id}")

    kept_task = tasks[keep_index]
    dropped_task = tasks[drop_index]
    if kept_task["status"] not in {"success", "fail"} or dropped_task["status"] not in {"success", "fail"}:
        raise ValueError("only closed goals can be merged")
    if kept_task["goal_type"] != dropped_task["goal_type"]:
        raise ValueError("only goals with the same goal_type can be merged")
    if dropped_task.get("supersedes_goal_id") == keep_task_id:
        raise ValueError("merge would create a supersession cycle")
    return keep_index, drop_index, kept_task, dropped_task


def _verify_merge_supersession(
    tasks: list[dict[str, Any]],
    keep_task_id: str,
    drop_task_id: str,
) -> None:
    """Simulate the merge on a copy and validate the supersession graph stays acyclic."""
    simulated_tasks = [dict(task) for task in tasks]
    simulated_kept_task = next(task for task in simulated_tasks if task["goal_id"] == keep_task_id)
    simulated_dropped_task = next(task for task in simulated_tasks if task["goal_id"] == drop_task_id)
    if simulated_kept_task.get("supersedes_goal_id") is None:
        simulated_kept_task["supersedes_goal_id"] = simulated_dropped_task.get("supersedes_goal_id")
    for task in simulated_tasks:
        if task.get("supersedes_goal_id") == drop_task_id:
            task["supersedes_goal_id"] = keep_task_id
    simulated_tasks = [task for task in simulated_tasks if task["goal_id"] != drop_task_id]
    try:
        validate_goal_supersession_graph(simulated_tasks)
    except ValueError as exc:
        raise ValueError("merge would create a supersession cycle") from exc


def _merge_kept_task_fields(kept_task: dict[str, Any], dropped_task: dict[str, Any]) -> None:
    kept_task["attempts"] = int(kept_task["attempts"]) + int(dropped_task["attempts"])
    kept_task["started_at"] = choose_earliest_timestamp(kept_task.get("started_at"), dropped_task.get("started_at"))
    kept_task["finished_at"] = choose_latest_timestamp(kept_task.get("finished_at"), dropped_task.get("finished_at"))
    kept_task["cost_usd"] = combine_optional_cost(kept_task.get("cost_usd"), dropped_task.get("cost_usd"))
    kept_task["input_tokens"] = combine_optional_tokens(kept_task.get("input_tokens"), dropped_task.get("input_tokens"))
    kept_task["cached_input_tokens"] = combine_optional_tokens(
        kept_task.get("cached_input_tokens"), dropped_task.get("cached_input_tokens")
    )
    kept_task["output_tokens"] = combine_optional_tokens(kept_task.get("output_tokens"), dropped_task.get("output_tokens"))
    kept_task["tokens_total"] = combine_optional_tokens(kept_task.get("tokens_total"), dropped_task.get("tokens_total"))
    kept_task["notes"] = build_merged_notes(kept_task, dropped_task)
    if kept_task.get("supersedes_goal_id") is None:
        kept_task["supersedes_goal_id"] = dropped_task.get("supersedes_goal_id")
    if kept_task.get("agent_name") is None:
        kept_task["agent_name"] = dropped_task.get("agent_name")

    if kept_task["status"] == "success":
        kept_task["failure_reason"] = None
    elif kept_task.get("failure_reason") is None:
        kept_task["failure_reason"] = dropped_task.get("failure_reason")


def _rehome_entries_and_resolve_model(
    data: dict[str, Any],
    kept_task: dict[str, Any],
    keep_task_id: str,
    drop_task_id: str,
) -> None:
    entries: list[dict[str, Any]] = data["entries"]
    for entry in entries:
        if entry.get("goal_id") == drop_task_id:
            entry["goal_id"] = keep_task_id
            validate_entry_record(entry)
    kept_entries = [entry for entry in entries if entry.get("goal_id") == keep_task_id]
    kept_entry_models = [entry.get("model") for entry in kept_entries]
    if kept_entry_models and all(model is not None for model in kept_entry_models):
        distinct_models = {str(model).strip() for model in kept_entry_models if model is not None}
        kept_task["model"] = distinct_models.pop() if len(distinct_models) == 1 else None
    else:
        kept_task["model"] = None


def merge_tasks(data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = data["goals"]
    _, drop_index, kept_task, dropped_task = _validate_merge_preconditions(
        tasks, keep_task_id, drop_task_id
    )
    _verify_merge_supersession(tasks, keep_task_id, drop_task_id)
    _merge_kept_task_fields(kept_task, dropped_task)
    _rehome_entries_and_resolve_model(data, kept_task, keep_task_id, drop_task_id)
    validate_goal_record(kept_task)
    for task in tasks:
        if task.get("supersedes_goal_id") == drop_task_id:
            task["supersedes_goal_id"] = keep_task_id
            validate_goal_record(task)
    del tasks[drop_index]
    return kept_task
