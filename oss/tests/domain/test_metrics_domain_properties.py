"""Property-based tests for the aggregation layer (recompute_summary).

Each property asserts an invariant that must hold across every well-formed
(goals, entries) pair. The strategies in ``tests/strategies/domain`` emit only
records that satisfy ``validate_goal_record`` / ``validate_entry_record`` so
the aggregation code under test runs the same validation path it does in
production.
"""
from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from strategies.domain import goals_and_entries

from ai_agents_metrics.domain.aggregation import recompute_summary

if TYPE_CHECKING:
    import random

# The aggregation layer is pure arithmetic (no I/O); 20 draws cover the
# numerical corner cases. Per-test timeout overrides pyproject.toml's 5s cap.
AGGREGATION_SETTINGS = settings(max_examples=20, deadline=None)


def _run_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Run ``recompute_summary`` on a deep copy; return the resulting summary block.

    A deep copy is mandatory because ``recompute_summary`` mutates the passed
    dict (adds ``summary``). Hypothesis reuses drawn values across the shrinker
    cycle, so mutating the input would make later draws observe state from
    earlier draws.
    """
    working = copy.deepcopy(data)
    recompute_summary(working)
    return working["summary"]


def _is_numeric_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ── 1. Empty-case robustness ────────────────────────────────────────────────


def test_empty_data_produces_zero_summary() -> None:
    summary = _run_summary({"goals": [], "entries": []})
    assert summary["closed_tasks"] == 0
    assert summary["successes"] == 0
    assert summary["fails"] == 0
    assert summary["total_attempts"] == 0
    assert summary["success_rate"] is None
    assert summary["attempts_per_closed_task"] is None
    assert summary["entries"]["closed_entries"] == 0
    # Every by_goal_type sub-block must also be empty.
    for sub in summary["by_goal_type"].values():
        assert sub["closed_tasks"] == 0
        assert sub["success_rate"] is None


# ── 2. Order-invariance ─────────────────────────────────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=6, max_entries_per_goal=2), st.randoms())
def test_summary_is_order_invariant(data: dict[str, Any], rng: random.Random) -> None:
    baseline = _run_summary(data)
    shuffled = copy.deepcopy(data)
    rng.shuffle(shuffled["goals"])
    rng.shuffle(shuffled["entries"])
    reshuffled_summary = _run_summary(shuffled)
    # Compare only the scalar counts and rates — nested by_model uses model
    # name as key, so dict equality already handles reordering there.
    for field in (
        "closed_tasks",
        "successes",
        "fails",
        "total_attempts",
        "total_tokens",
        "success_rate",
        "attempts_per_closed_task",
    ):
        assert baseline[field] == reshuffled_summary[field], field


# ── 3. Partition: successes + fails == closed_tasks ─────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=8, max_entries_per_goal=2))
def test_partition_holds_top_level_and_breakdowns(data: dict[str, Any]) -> None:
    summary = _run_summary(data)
    assert summary["successes"] + summary["fails"] == summary["closed_tasks"]
    for block in summary["by_goal_type"].values():
        assert block["successes"] + block["fails"] == block["closed_tasks"]
    for block in summary["by_model"].values():
        assert block["successes"] + block["fails"] == block["closed_tasks"]
    entries = summary["entries"]
    assert entries["successes"] + entries["fails"] == entries["closed_entries"]


# ── 4. Rate bounds ──────────────────────────────────────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=6, max_entries_per_goal=2))
def test_rates_are_bounded_or_none_when_no_closed(data: dict[str, Any]) -> None:
    summary = _run_summary(data)
    blocks: list[dict[str, Any]] = [
        summary,
        *summary["by_goal_type"].values(),
        *summary["by_model"].values(),
    ]
    for block in blocks:
        rate = block["success_rate"]
        if block["closed_tasks"] == 0:
            assert rate is None
        else:
            assert rate is not None
            assert 0.0 <= rate <= 1.0


# ── 5. Success-rate formula ─────────────────────────────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=6, max_entries_per_goal=2))
def test_success_rate_matches_successes_over_closed(data: dict[str, Any]) -> None:
    summary = _run_summary(data)
    blocks: list[dict[str, Any]] = [
        summary,
        *summary["by_goal_type"].values(),
        *summary["by_model"].values(),
    ]
    for block in blocks:
        if block["closed_tasks"] > 0:
            expected = block["successes"] / block["closed_tasks"]
            assert math.isclose(block["success_rate"], expected, rel_tol=1e-9, abs_tol=1e-12)


# ── 6. Attempts-per-closed-task formula ─────────────────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=6, max_entries_per_goal=2))
def test_attempts_per_closed_task_matches_total_over_closed(data: dict[str, Any]) -> None:
    summary = _run_summary(data)
    blocks: list[dict[str, Any]] = [
        summary,
        *summary["by_goal_type"].values(),
        *summary["by_model"].values(),
    ]
    for block in blocks:
        closed = block["closed_tasks"]
        if closed == 0:
            assert block["attempts_per_closed_task"] is None
        else:
            expected = block["total_attempts"] / closed
            assert math.isclose(block["attempts_per_closed_task"], expected, rel_tol=1e-9, abs_tol=1e-12)


# ── 7. Cost-completeness subset ─────────────────────────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=6, max_entries_per_goal=2))
def test_cost_completeness_is_a_subset_chain(data: dict[str, Any]) -> None:
    summary = _run_summary(data)
    # complete_cost_successes ≤ known_cost_successes ≤ successes.
    # "complete" requires every goal in the chain to have cost_usd; "known"
    # accepts at least one known value. Both must be a subset of successes.
    blocks: list[dict[str, Any]] = [
        summary,
        *summary["by_goal_type"].values(),
        *summary["by_model"].values(),
    ]
    for block in blocks:
        assert block["complete_cost_successes"] <= block["known_cost_successes"]
        assert block["known_cost_successes"] <= block["successes"]
        # Mirror on tokens.
        assert block["complete_token_successes"] <= block["known_token_successes"]
        assert block["known_token_successes"] <= block["successes"]


# ── 8. Non-negativity of all count fields ───────────────────────────────────


@pytest.mark.timeout(30)
@AGGREGATION_SETTINGS
@given(goals_and_entries(max_goals=6, max_entries_per_goal=2))
def test_all_count_fields_are_non_negative(data: dict[str, Any]) -> None:
    summary = _run_summary(data)
    count_fields = (
        "closed_tasks",
        "successes",
        "fails",
        "total_attempts",
        "total_input_tokens",
        "total_cached_input_tokens",
        "total_output_tokens",
        "total_tokens",
        "known_cost_successes",
        "complete_cost_successes",
        "known_token_successes",
        "known_token_breakdown_successes",
        "complete_token_successes",
        "complete_token_breakdown_successes",
        "model_summary_goals",
        "model_complete_goals",
        "mixed_model_goals",
    )
    for block_name, block in [("top", summary), *summary["by_goal_type"].items(), *summary["by_model"].items()]:
        for field in count_fields:
            value = block[field]
            assert _is_numeric_count(value), f"{block_name}.{field} not an int"
            assert value >= 0, f"{block_name}.{field} is negative"
    # Entry summary block has its own set of counts.
    entries = summary["entries"]
    for field in ("closed_entries", "successes", "fails", "total_input_tokens", "total_tokens"):
        assert _is_numeric_count(entries[field])
        assert entries[field] >= 0
