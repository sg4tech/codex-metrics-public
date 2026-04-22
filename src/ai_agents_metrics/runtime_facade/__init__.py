"""Orchestration facade: the concrete ``CommandRuntime`` used by CLI command handlers.

The facade is layered into submodules by concern:
  - ``orchestration`` — path constants, history-pipeline wrappers, workflow, init/bootstrap
  - ``costs`` — usage-cost resolution and cost-audit coverage
  - ``mutations`` — upsert/sync/merge pipelines

This ``__init__`` re-exports the full public surface so ``from ai_agents_metrics
import runtime_facade`` and ``runtime_facade.X`` continue to resolve every
symbol without callers knowing about the submodule layout.
"""
from ai_agents_metrics.cost_audit import render_cost_audit_report_json
from ai_agents_metrics.domain import (
    GoalUsageResolution,
    load_metrics,
    recompute_summary,
)
from ai_agents_metrics.git_state import (
    ActiveTaskResolution,
    detect_started_work,
)
from ai_agents_metrics.history.audit import (
    audit_history,
    render_audit_report,
    render_audit_report_json,
)
from ai_agents_metrics.history.classify import render_classify_summary_json
from ai_agents_metrics.history.compare import (
    compare_metrics_to_history,
    read_history_signals,
    render_history_compare_report,
    render_history_compare_report_json,
)
from ai_agents_metrics.history.derive import render_derive_summary_json
from ai_agents_metrics.history.ingest import render_ingest_summary_json
from ai_agents_metrics.history.normalize import render_normalize_summary_json
from ai_agents_metrics.pricing_runtime import (
    load_effective_pricing,
    resolve_effective_pricing_path,
)
from ai_agents_metrics.reporting import (
    print_summary,
    render_summary_json,
)
from ai_agents_metrics.retro_timeline import (
    derive_retro_timeline,
    render_retro_timeline_report,
    render_retro_timeline_report_json,
)
from ai_agents_metrics.runtime_facade.costs import (
    audit_cost_coverage,
    resolve_goal_usage_updates,
    resolve_usage_costs,
)
from ai_agents_metrics.runtime_facade.mutations import (
    merge_tasks,
    sync_codex_usage,
    sync_usage,
    upsert_task,
)
from ai_agents_metrics.runtime_facade.orchestration import (
    CLAUDE_ROOT,
    CODEX_LOGS_PATH,
    CODEX_STATE_PATH,
    EVENTS_NDJSON_PATH,
    METRICS_JSON_PATH,
    RAW_WAREHOUSE_PATH,
    REPORT_MD_PATH,
    bootstrap_project,
    classify_codex_history,
    derive_codex_history,
    ensure_active_task,
    get_active_goals,
    ingest_codex_history,
    init_files,
    normalize_codex_history,
    resolve_workflow_resolution,
    save_report,
    verify_public_boundary,
)
from ai_agents_metrics.storage import metrics_mutation_lock
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
    "resolve_usage_costs",
    "resolve_usage_session_window",
    "resolve_workflow_resolution",
    "save_report",
    "sync_codex_usage",
    "sync_usage",
    "upsert_task",
    "verify_public_boundary",
]
