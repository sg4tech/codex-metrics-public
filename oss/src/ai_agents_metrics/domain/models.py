"""Canonical data schemas used across the ledger, warehouse, and facade layers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple, TypeVar

ALLOWED_STATUSES = {"in_progress", "success", "fail"}
ALLOWED_TASK_TYPES = {"product", "retro", "meta"}
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
ALLOWED_RESULT_FITS = {"exact_fit", "partial_fit", "miss"}


# GoalRecord / AttemptEntryRecord / EffectiveGoalRecord mirror the canonical
# ndjson goal and attempt schemas field-for-field. Splitting them into nested
# structures would break dict round-tripping used throughout the codebase.
@dataclass
class GoalRecord:  # pylint: disable=too-many-instance-attributes
    goal_id: str
    title: str
    goal_type: str
    supersedes_goal_id: str | None
    status: str
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    cost_usd: float | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None
    agent_name: str | None = None
    result_fit: str | None = None
    model: str | None = None


@dataclass
class AttemptEntryRecord:  # pylint: disable=too-many-instance-attributes
    entry_id: str
    goal_id: str
    entry_type: str
    inferred: bool
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    cost_usd: float | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    tokens_total: int | None
    failure_reason: str | None
    notes: str | None
    agent_name: str | None = None
    model: str | None = None


@dataclass
class EffectiveGoalRecord:  # pylint: disable=too-many-instance-attributes
    goal_id: str
    title: str
    goal_type: str
    status: str
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    cost_usd: float | None
    cost_usd_known: float | None
    cost_complete: bool
    input_tokens: int | None
    input_tokens_known: int | None
    cached_input_tokens: int | None
    cached_input_tokens_known: int | None
    output_tokens: int | None
    output_tokens_known: int | None
    token_breakdown_complete: bool
    tokens_total: int | None
    tokens_total_known: int | None
    tokens_complete: bool
    failure_reason: str | None
    notes: str | None
    supersedes_goal_id: str | None
    result_fit: str | None = None
    model: str | None = None
    model_complete: bool = False
    model_consistent: bool = False


StatusRecordT = TypeVar("StatusRecordT", GoalRecord, AttemptEntryRecord, EffectiveGoalRecord)


class GoalUsageResolution(NamedTuple):
    """Usage/cost recovery outcome produced by :func:`resolve_goal_usage_updates`.

    Subclassing ``NamedTuple`` preserves the positional tuple contract used
    by tests (``*_, detected = resolve_goal_usage_updates(...)``) while giving
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


EMPTY_GOAL_USAGE_RESOLUTION = GoalUsageResolution(
    usage_cost_usd=None,
    usage_total_tokens=None,
    usage_input_tokens=None,
    usage_cached_input_tokens=None,
    usage_output_tokens=None,
    usage_model=None,
    auto_cost_usd=None,
    auto_total_tokens=None,
    auto_input_tokens=None,
    auto_cached_input_tokens=None,
    auto_output_tokens=None,
    auto_model=None,
    detected_agent_name=None,
)


# ManualGoalUpdates bundles the user-facing fields the `update` / `start-task`
# / `finish-task` CLI flags populate directly, so apply_goal_updates can take
# one structured argument instead of ~18 individual kwargs.
@dataclass(frozen=True)
class ManualGoalUpdates:  # pylint: disable=too-many-instance-attributes
    title: str | None = None
    task_type: str | None = None
    status: str | None = None
    attempts_delta: int | None = None
    attempts_abs: int | None = None
    cost_usd_add: float | None = None
    cost_usd_set: float | None = None
    input_tokens_add: int | None = None
    cached_input_tokens_add: int | None = None
    output_tokens_add: int | None = None
    tokens_add: int | None = None
    tokens_set: int | None = None
    failure_reason: str | None = None
    result_fit: str | None = None
    notes: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    model: str | None = None
    agent_name: str | None = None


__all__ = [
    "ALLOWED_FAILURE_REASONS",
    "ALLOWED_RESULT_FITS",
    "ALLOWED_STATUSES",
    "ALLOWED_TASK_TYPES",
    "AttemptEntryRecord",
    "EMPTY_GOAL_USAGE_RESOLUTION",
    "EffectiveGoalRecord",
    "GoalRecord",
    "GoalUsageResolution",
    "ManualGoalUpdates",
    "StatusRecordT",
]
