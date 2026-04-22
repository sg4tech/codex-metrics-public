"""Hypothesis strategies for GoalRecord and AttemptEntryRecord dicts.

Every generated dict satisfies the full validation contract in
``ai_agents_metrics.domain.validation`` — ``validate_goal_record`` and
``validate_entry_record`` can be called on the output without raising.

Entries are drawn against a pool of goal ids so the foreign-key constraint
between ``AttemptEntryRecord.goal_id`` and the canonical goal list holds.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import strategies as st

from ai_agents_metrics.domain.models import (
    ALLOWED_FAILURE_REASONS,
    ALLOWED_RESULT_FITS,
    ALLOWED_STATUSES,
    ALLOWED_TASK_TYPES,
)

_FAILURE_REASONS: tuple[str, ...] = tuple(sorted(ALLOWED_FAILURE_REASONS))
_RESULT_FITS: tuple[str, ...] = tuple(sorted(ALLOWED_RESULT_FITS))
_STATUSES: tuple[str, ...] = tuple(sorted(ALLOWED_STATUSES))
_TASK_TYPES: tuple[str, ...] = tuple(sorted(ALLOWED_TASK_TYPES))

# Anchor the generated datetimes to 2025 so no leap-second or pre-epoch edge
# cases sneak in. The spread (+/- 90 days) is wide enough to exercise ordering
# logic without making the test surface noise.
_EPOCH = datetime(2025, 6, 1, tzinfo=UTC)


def _non_empty_text(max_size: int = 20) -> st.SearchStrategy[str]:
    # Use printable alphabet excluding whitespace-only strings; validators reject
    # blank strings after `.strip()` for ids, titles, models, agent_names.
    return st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=max_size,
    ).filter(lambda s: s.strip() != "")


def _iso_ts(offset_days: float) -> str:
    return (_EPOCH + timedelta(days=offset_days)).isoformat()


@st.composite
def _started_finished_pair(
    draw: st.DrawFn, *, status: str
) -> tuple[str | None, str | None]:
    """Draw (started_at, finished_at) ISO strings consistent with business rules."""
    has_started = draw(st.booleans())
    started_offset = draw(st.floats(min_value=-30.0, max_value=30.0, allow_nan=False))
    duration = draw(st.floats(min_value=0.0, max_value=30.0, allow_nan=False))
    if status == "in_progress":
        started_at = _iso_ts(started_offset) if has_started else None
        return started_at, None
    # Closed goals (success / fail) carry both timestamps.
    return _iso_ts(started_offset), _iso_ts(started_offset + duration)


@st.composite
def _token_breakdown(
    draw: st.DrawFn,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Draw (input, cached_input, output, total) respecting the total-sum invariant."""
    input_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)))
    cached_input_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)))
    output_tokens = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)))
    if input_tokens is not None and cached_input_tokens is not None and output_tokens is not None:
        minimum_total = input_tokens + cached_input_tokens + output_tokens
        tokens_total = draw(
            st.one_of(st.none(), st.integers(min_value=minimum_total, max_value=minimum_total + 10_000))
        )
    else:
        tokens_total = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=30_000)))
    return input_tokens, cached_input_tokens, output_tokens, tokens_total


@st.composite
def goal_record_dicts(
    draw: st.DrawFn,
    *,
    goal_id: str | None = None,
    supersedes_pool: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Draw a dict that satisfies ``validate_goal_record``.

    ``goal_id`` pins the generated goal's id (useful when building a list of
    goals with unique ids). ``supersedes_pool`` lets the caller restrict
    ``supersedes_goal_id`` to a set of previously-drawn goal ids so the
    supersession graph never references unknown ids.
    """
    resolved_goal_id = goal_id or draw(_non_empty_text())
    status = draw(st.sampled_from(_STATUSES))
    goal_type = draw(st.sampled_from(_TASK_TYPES))
    # Closed goals must have attempts >= 1 per validate_task_business_rules.
    attempts_min = 1 if status in {"success", "fail"} else 0
    attempts = draw(st.integers(min_value=attempts_min, max_value=10))
    started_at, finished_at = draw(_started_finished_pair(status=status))
    input_tokens, cached_input_tokens, output_tokens, tokens_total = draw(_token_breakdown())
    failure_reason = draw(st.sampled_from(_FAILURE_REASONS)) if status == "fail" else None
    result_fit = _draw_result_fit(draw, goal_type=goal_type, status=status)
    supersedes_goal_id = _draw_supersedes(draw, pool=supersedes_pool, own_id=resolved_goal_id)

    return {
        "goal_id": resolved_goal_id,
        "title": draw(_non_empty_text(max_size=30)),
        "goal_type": goal_type,
        "supersedes_goal_id": supersedes_goal_id,
        "status": status,
        "attempts": attempts,
        "started_at": started_at,
        "finished_at": finished_at,
        "cost_usd": draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1_000.0, allow_nan=False))),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "tokens_total": tokens_total,
        "failure_reason": failure_reason,
        "notes": draw(st.one_of(st.none(), st.text(max_size=40))),
        "agent_name": draw(st.one_of(st.none(), _non_empty_text(max_size=15))),
        "result_fit": result_fit,
        "model": draw(st.one_of(st.none(), _non_empty_text(max_size=20))),
    }


def _draw_result_fit(draw: st.DrawFn, *, goal_type: str, status: str) -> str | None:
    """result_fit is only legal for product goals that are closed, with status-specific options."""
    if goal_type != "product" or status == "in_progress":
        return None
    if status == "success":
        non_miss = tuple(f for f in _RESULT_FITS if f != "miss")
        return draw(st.sampled_from(non_miss + (None,)))
    return draw(st.sampled_from(("miss", None)))


def _draw_supersedes(
    draw: st.DrawFn, *, pool: tuple[str, ...], own_id: str
) -> str | None:
    candidates = tuple(g for g in pool if g != own_id)
    if not candidates:
        return None
    return draw(st.one_of(st.none(), st.sampled_from(candidates)))


@st.composite
def goal_list_dicts(
    draw: st.DrawFn,
    *,
    min_size: int = 0,
    max_size: int = 8,
) -> list[dict[str, Any]]:
    """Draw a list of goal dicts with unique goal_ids and an acyclic supersedes graph.

    Supersession follows draw order: goal N can only reference goals 0..N-1.
    That guarantees the graph stays a DAG and validators pass.
    """
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    goal_ids = [f"g-{i:04d}-{draw(_non_empty_text(max_size=6))}" for i in range(size)]
    # De-duplicate while preserving order — validator rejects duplicate goal_ids.
    seen: set[str] = set()
    unique_ids: list[str] = []
    for gid in goal_ids:
        if gid not in seen:
            unique_ids.append(gid)
            seen.add(gid)

    goals: list[dict[str, Any]] = []
    for index, gid in enumerate(unique_ids):
        pool = tuple(unique_ids[:index])
        goals.append(draw(goal_record_dicts(goal_id=gid, supersedes_pool=pool)))
    return goals


@st.composite
def entry_record_dicts(
    draw: st.DrawFn,
    *,
    goal_id: str,
    entry_id: str | None = None,
) -> dict[str, Any]:
    """Draw a dict that satisfies ``validate_entry_record`` for the given goal."""
    resolved_entry_id = entry_id or f"{goal_id}-attempt-{draw(st.integers(min_value=1, max_value=9)):03d}"
    status = draw(st.sampled_from(_STATUSES))
    inferred = draw(st.booleans())
    started_at, finished_at = draw(_started_finished_pair(status=status))
    input_tokens, cached_input_tokens, output_tokens, tokens_total = draw(_token_breakdown())
    # Entry validator allows a null failure_reason on fail when inferred=True
    # (auto-closed retry); explicit fails must carry a reason.
    if status == "fail" and not inferred:
        failure_reason: str | None = draw(st.sampled_from(_FAILURE_REASONS))
    elif status == "fail":
        failure_reason = draw(st.one_of(st.none(), st.sampled_from(_FAILURE_REASONS)))
    else:
        failure_reason = None

    return {
        "entry_id": resolved_entry_id,
        "goal_id": goal_id,
        "entry_type": draw(st.sampled_from(_TASK_TYPES)),
        "inferred": inferred,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "cost_usd": draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=500.0, allow_nan=False))),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "tokens_total": tokens_total,
        "failure_reason": failure_reason,
        "notes": draw(st.one_of(st.none(), st.text(max_size=40))),
        "agent_name": draw(st.one_of(st.none(), _non_empty_text(max_size=15))),
        "model": draw(st.one_of(st.none(), _non_empty_text(max_size=20))),
    }


@st.composite
def goals_and_entries(
    draw: st.DrawFn,
    *,
    min_goals: int = 0,
    max_goals: int = 8,
    max_entries_per_goal: int = 3,
) -> dict[str, Any]:
    """Draw ``{"goals": [...], "entries": [...]}`` with entries pinned to drawn goal ids."""
    goals = draw(goal_list_dicts(min_size=min_goals, max_size=max_goals))
    entries: list[dict[str, Any]] = []
    for goal in goals:
        entry_count = draw(st.integers(min_value=0, max_value=max_entries_per_goal))
        entries.extend(
            draw(
                entry_record_dicts(
                    goal_id=goal["goal_id"],
                    entry_id=f"{goal['goal_id']}-attempt-{entry_index + 1:03d}",
                )
            )
            for entry_index in range(entry_count)
        )
    return {"goals": goals, "entries": entries}
