from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

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


@dataclass
class GoalRecord:
    goal_id: str
    title: str
    goal_type: str
    supersedes_goal_id: str | None
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
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
class AttemptEntryRecord:
    entry_id: str
    goal_id: str
    entry_type: str
    inferred: bool
    status: str
    started_at: str | None
    finished_at: str | None
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
class EffectiveGoalRecord:
    goal_id: str
    title: str
    goal_type: str
    status: str
    attempts: int
    started_at: str | None
    finished_at: str | None
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
