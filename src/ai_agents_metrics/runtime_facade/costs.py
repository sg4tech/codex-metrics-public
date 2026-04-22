"""Usage-cost resolution and cost-audit coverage helpers."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.cost_audit import (
    CostAuditContext,
    CostAuditReport,
)
from ai_agents_metrics.cost_audit import (
    audit_cost_coverage as _run_audit_cost_coverage,
)
from ai_agents_metrics.domain import (
    GoalUsageResolution,
    round_usd,
    validate_non_negative_int,
)
from ai_agents_metrics.runtime_facade.orchestration import CLAUDE_ROOT
from ai_agents_metrics.usage.backends import (
    ClaudeUsageBackend,
    UsageBackend,
    select_usage_backend,
)
from ai_agents_metrics.usage.backends import (
    resolve_usage_window as resolve_backend_usage_window,
)
from ai_agents_metrics.usage.resolution import (
    find_usage_thread_id,
    load_pricing,
    resolve_pricing_model_alias,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ai_agents_metrics.domain import GoalRecord


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
    cached_input_cost = Decimal(0)
    if cached_rate is not None:
        cached_input_cost = Decimal(str(cached_rate)) * Decimal(cached_input_tokens_value) / Decimal(1_000_000)
    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(output_tokens_value) / Decimal(1_000_000)
    total_cost = round_usd(input_cost + cached_input_cost + output_cost)
    total_tokens = input_tokens_value + cached_input_tokens_value + output_tokens_value
    return total_cost, total_tokens, input_tokens_value, cached_input_tokens_value, output_tokens_value, model


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

        if (auto_cost_usd is not None or auto_total_tokens is not None) and task.agent_name is None:
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
