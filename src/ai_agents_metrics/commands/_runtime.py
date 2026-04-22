"""Protocol describing the runtime surface CLI handlers depend on."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from ai_agents_metrics.cost_audit import CostAuditReport
    from ai_agents_metrics.history.audit import AuditReport
    from ai_agents_metrics.history.classify import ClassifySummary
    from ai_agents_metrics.history.compare import (
        HistoryCompareReport,
        HistorySignals,
    )
    from ai_agents_metrics.history.derive import DeriveSummary
    from ai_agents_metrics.history.ingest import IngestSummary
    from ai_agents_metrics.history.normalize import NormalizeSummary
    from ai_agents_metrics.retro_timeline import RetroTimelineReport
    from ai_agents_metrics.usage.backends import UsageBackend
    from ai_agents_metrics.workflow_fsm import WorkflowEvent


# CommandRuntime aggregates the entire runtime surface that handle_* command
# functions depend on. 40 methods reflect the breadth of operations the CLI
# dispatches, not an architectural issue. Splitting would fragment the single
# type hint each handler uses, without reducing coupling.
class CommandRuntime(Protocol):  # pylint: disable=too-many-public-methods
    def init_files(self, metrics_path: Path, report_path: Path | None, force: bool = False) -> None: ...
    # pylint: disable-next=too-many-arguments
    def bootstrap_project(
        self,
        *,
        target_dir: Path,
        metrics_path: Path,
        report_path: Path | None,
        policy_path: Path,
        command_path: Path,
        agents_path: Path,
        force: bool = False,
        dry_run: bool = False,
    ) -> list[str]: ...
    # pylint: disable-next=too-many-arguments
    def sync_usage(
        self,
        data: dict[str, Any],
        *,
        cwd: Path,
        pricing_path: Path,
        usage_state_path: Path,
        usage_logs_path: Path,
        usage_thread_id: str | None,
        usage_backend: UsageBackend | None = None,
        claude_root: Path = ...,
    ) -> int: ...
    def sync_codex_usage(
        self,
        data: dict[str, Any],
        *,
        cwd: Path,
        pricing_path: Path,
        codex_state_path: Path,
        codex_logs_path: Path,
        codex_thread_id: str | None,
    ) -> int: ...
    def save_report(self, path: Path, data: dict[str, Any]) -> None: ...
    def detect_started_work(self, cwd: Path) -> Any: ...
    def ensure_active_task(self, data: dict[str, Any], cwd: Path) -> Any: ...
    def get_active_goals(self, data: dict[str, Any]) -> list[dict[str, Any]]: ...
    def resolve_workflow_resolution(self, data: dict[str, Any], cwd: Path, event: WorkflowEvent) -> Any: ...
    def ingest_codex_history(self, source_root: Path, warehouse_path: Path, source: str = ...) -> Any: ...
    def normalize_codex_history(self, warehouse_path: Path) -> Any: ...
    def classify_codex_history(self, warehouse_path: Path) -> Any: ...
    def derive_codex_history(self, warehouse_path: Path) -> Any: ...
    def verify_public_boundary(self, *, repo_root: Path, rules_path: Path) -> Any: ...
    def audit_cost_coverage(
        self,
        data: dict[str, Any],
        *,
        pricing_path: Path,
        codex_state_path: Path,
        codex_logs_path: Path,
        codex_thread_id: str | None,
        cwd: Path,
        claude_root: Path = ...,
    ) -> CostAuditReport: ...
    def load_metrics(self, path: Path) -> dict[str, Any]: ...
    def recompute_summary(self, data: dict[str, Any]) -> None: ...
    def print_summary(self, data: dict[str, Any], history_signals: HistorySignals | None = ...) -> None: ...
    def render_summary_json(self, data: dict[str, Any], history_signals: HistorySignals | None = ...) -> str: ...
    def read_history_signals(self, warehouse_path: Path, project_cwd: Path, data: dict[str, Any]) -> HistorySignals | None: ...
    def audit_history(self, data: dict[str, Any]) -> AuditReport: ...
    def render_audit_report(self, report: AuditReport) -> str: ...
    def render_audit_report_json(self, report: AuditReport) -> str: ...
    def compare_metrics_to_history(
        self,
        data: dict[str, Any],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
    ) -> HistoryCompareReport: ...
    def render_history_compare_report(self, report: HistoryCompareReport) -> str: ...
    def render_history_compare_report_json(self, report: HistoryCompareReport) -> str: ...
    def metrics_mutation_lock(self, path: Path) -> Any: ...
    def render_ingest_summary_json(self, summary: IngestSummary) -> str: ...
    def render_normalize_summary_json(self, summary: NormalizeSummary) -> str: ...
    def render_classify_summary_json(self, summary: ClassifySummary) -> str: ...
    def render_derive_summary_json(self, summary: DeriveSummary) -> str: ...
    def derive_retro_timeline(
        self,
        data: dict[str, Any],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
        window_size: int,
    ) -> RetroTimelineReport: ...
    def render_retro_timeline_report(self, report: RetroTimelineReport) -> str: ...
    def render_retro_timeline_report_json(self, report: RetroTimelineReport) -> str: ...
    def render_cost_audit_report_json(self, report: CostAuditReport) -> str: ...
    def load_effective_pricing(self, *, cwd: Path, pricing_path: Path | None = None) -> dict[str, dict[str, float | None]]: ...
    def resolve_effective_pricing_path(self, *, cwd: Path, pricing_path: Path | None = None) -> Path: ...
    def resolve_pricing_path(self, cwd: Path) -> Path: ...
    def merge_tasks(self, data: dict[str, Any], keep_task_id: str, drop_task_id: str) -> dict[str, Any]: ...
    # upsert_task mirrors apply_goal_updates' signature; both are tracked as
    # candidates for a sub-dataclass refactor once update precedence rules
    # stabilise.
    # pylint: disable-next=too-many-arguments,too-many-locals
    def upsert_task(
        self,
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
        claude_root: Path = ...,
    ) -> dict[str, Any]: ...


_COMMAND_TO_EVENT_TYPE: dict[str, str] = {
    "start-task": "goal_started",
    "continue-task": "goal_continued",
    "finish-task": "goal_finished",
}


def _command_to_event_type(command: str | None) -> str:
    return _COMMAND_TO_EVENT_TYPE.get(command or "", "goal_updated")
