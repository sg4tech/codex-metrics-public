"""CLI command handlers (one ``handle_*`` per subcommand).

Handlers are grouped by functional cluster in submodules; this ``__init__``
re-exports the full public surface so that ``from ai_agents_metrics import
commands`` continues to resolve every ``handle_*`` and ``CommandRuntime``
symbol without callers knowing about the submodule layout.
"""
from ai_agents_metrics.commands._runtime import CommandRuntime
from ai_agents_metrics.commands.history import (
    handle_audit_cost_coverage,
    handle_audit_history,
    handle_classify_codex_history,
    handle_compare_metrics_to_history,
    handle_derive_codex_history,
    handle_derive_retro_timeline,
    handle_history_update,
    handle_ingest_codex_history,
    handle_normalize_codex_history,
)
from ai_agents_metrics.commands.install import (
    handle_bootstrap,
    handle_init,
    handle_install_self,
)
from ai_agents_metrics.commands.misc import (
    handle_ensure_active_task,
    handle_show,
    handle_sync_codex_usage,
    handle_sync_usage,
    handle_verify_public_boundary,
)
from ai_agents_metrics.commands.report import (
    handle_render_html,
    handle_render_report,
)
from ai_agents_metrics.commands.tasks import (
    handle_continue_task,
    handle_finish_task,
    handle_merge_tasks,
    handle_start_task,
    handle_update,
)

__all__ = [
    "CommandRuntime",
    "handle_audit_cost_coverage",
    "handle_audit_history",
    "handle_bootstrap",
    "handle_classify_codex_history",
    "handle_compare_metrics_to_history",
    "handle_continue_task",
    "handle_derive_codex_history",
    "handle_derive_retro_timeline",
    "handle_ensure_active_task",
    "handle_finish_task",
    "handle_history_update",
    "handle_ingest_codex_history",
    "handle_init",
    "handle_install_self",
    "handle_merge_tasks",
    "handle_normalize_codex_history",
    "handle_render_html",
    "handle_render_report",
    "handle_show",
    "handle_start_task",
    "handle_sync_codex_usage",
    "handle_sync_usage",
    "handle_update",
    "handle_verify_public_boundary",
]
