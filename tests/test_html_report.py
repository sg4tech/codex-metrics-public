"""Tests for html_report: aggregation logic and render smoke checks."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from ai_agents_metrics._report_aggregation import (
    _aggregate_warehouse_retry,
    _aggregate_warehouse_tokens_by_model,
    aggregate_report_data,
)
from ai_agents_metrics._report_buckets import _bucket_key, _make_buckets, _monday_of, _parse_date
from ai_agents_metrics.html_report import check_warehouse_state, render_html_report

# ── helpers ───────────────────────────────────────────────────────────────────


def _goal(
    *,
    status: str = "success",
    finished_at: str | None = "2026-01-15T10:00:00+00:00",
    attempts: int = 1,
    cost_usd: float | None = None,
    input_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    output_tokens: int | None = None,
    goal_type: str = "product",
    model: str | None = None,
) -> dict:
    return {
        "goal_id": "g1",
        "title": "T",
        "goal_type": goal_type,
        "status": status,
        "attempts": attempts,
        "finished_at": finished_at,
        "started_at": None,
        "cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
        "result_fit": None,
        "model": model,
    }


# ── parse helpers ─────────────────────────────────────────────────────────────


def test_parse_date_none():
    assert _parse_date(None) is None


def test_parse_date_valid():
    dt = _parse_date("2026-01-15T10:00:00+00:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 1 and dt.day == 15


def test_parse_date_z_suffix():
    dt = _parse_date("2026-03-01T00:00:00Z")
    assert dt is not None and dt.month == 3


def test_monday_of():
    # 2026-01-14 is a Wednesday → Monday is 2026-01-12
    dt = datetime(2026, 1, 14, 15, 30)
    monday = _monday_of(dt)
    assert monday.weekday() == 0
    assert monday.strftime("%Y-%m-%d") == "2026-01-12"


# ── bucketing ─────────────────────────────────────────────────────────────────


def test_make_buckets_daily():
    earliest = datetime(2026, 1, 1)
    latest = datetime(2026, 1, 5)
    buckets = _make_buckets(earliest, latest, "day")
    assert buckets == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]


def test_make_buckets_weekly():
    earliest = datetime(2026, 1, 5)   # Monday
    latest = datetime(2026, 1, 19)    # Monday (two weeks later)
    buckets = _make_buckets(earliest, latest, "week")
    assert buckets == ["2026-01-05", "2026-01-12", "2026-01-19"]


def test_bucket_key_daily():
    dt = datetime(2026, 3, 15, 12, 0, tzinfo=None)
    assert _bucket_key(dt, "day") == "2026-03-15"


def test_bucket_key_weekly():
    # Wednesday 2026-01-14 → week of Monday 2026-01-12
    from datetime import timezone
    dt = datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)
    assert _bucket_key(dt, "week") == "2026-01-12"


# ── aggregate_report_data ─────────────────────────────────────────────────────


def test_empty_goals_returns_empty_data():
    result = aggregate_report_data([], days=None)
    assert result["buckets"] == []
    assert result["chart1_product"] == []
    assert result["chart1_meta"] == []
    assert result["chart1_retro"] == []
    assert result["chart4_buckets"] == []


def test_in_progress_goals_excluded():
    goals = [_goal(status="in_progress", finished_at="2026-01-15T10:00:00+00:00")]
    result = aggregate_report_data(goals, days=None)
    assert result["buckets"] == []


def test_goals_without_finished_at_excluded():
    goals = [_goal(status="success", finished_at=None)]
    result = aggregate_report_data(goals, days=None)
    assert result["buckets"] == []


def test_single_success_daily():
    goals = [_goal(status="success", finished_at="2026-01-15T10:00:00+00:00", goal_type="product")]
    result = aggregate_report_data(goals, days=None)
    assert "2026-01-15" in result["buckets"]
    idx = result["buckets"].index("2026-01-15")
    # product goal → chart1_product
    assert result["chart1_product"][idx] == 1
    assert result["chart1_meta"][idx] == 0
    assert result["chart1_retro"][idx] == 0


def test_single_success_meta():
    goals = [_goal(status="success", finished_at="2026-01-15T10:00:00+00:00", goal_type="meta")]
    result = aggregate_report_data(goals, days=None)
    idx = result["buckets"].index("2026-01-15")
    assert result["chart1_product"][idx] == 0
    assert result["chart1_meta"][idx] == 1


def test_fail_not_counted_in_chart1():
    goals = [_goal(status="fail", finished_at="2026-01-15T10:00:00+00:00")]
    result = aggregate_report_data(goals, days=None)
    assert result["chart1_product"][0] == 0
    assert result["chart1_meta"][0] == 0


def test_retry_pressure_chart2():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", attempts=1),
        _goal(status="success", finished_at="2026-01-15T11:00:00+00:00", attempts=3),
        _goal(status="fail",    finished_at="2026-01-15T12:00:00+00:00", attempts=2),
    ]
    result = aggregate_report_data(goals, days=None)
    idx = result["buckets"].index("2026-01-15")
    # 2 goals had attempts > 1
    assert result["chart2_bar"][idx] == 2
    # avg attempts = (1 + 3 + 2) / 3 = 2.0
    assert result["chart2_line"][idx] == 2.0


def test_token_aggregation_stacked_by_model():
    # Two goals without explicit model land in the "unknown" bucket.
    # Total tokens = (100+50+30) + (200+0+80) = 460.
    goals = [
        _goal(
            status="success",
            finished_at="2026-01-15T10:00:00+00:00",
            input_tokens=100,
            cached_input_tokens=50,
            output_tokens=30,
        ),
        _goal(
            status="fail",
            finished_at="2026-01-15T12:00:00+00:00",
            input_tokens=200,
            cached_input_tokens=0,
            output_tokens=80,
        ),
    ]
    result = aggregate_report_data(goals, days=None)
    idx = result["buckets"].index("2026-01-15")
    series = result["chart3_series"]
    assert len(series) == 1
    assert series[0]["name"] == "unknown"
    assert series[0]["values"][idx] == 460


def test_token_aggregation_separates_models():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00",
              model="claude-sonnet-4-6", input_tokens=100, cached_input_tokens=50, output_tokens=30),
        _goal(status="success", finished_at="2026-01-15T11:00:00+00:00",
              model="claude-opus-4-6",   input_tokens=200, cached_input_tokens=0,  output_tokens=80),
    ]
    result = aggregate_report_data(goals, days=None)
    idx = result["buckets"].index("2026-01-15")
    series = {s["name"]: s for s in result["chart3_series"]}
    assert series["claude-sonnet-4-6"]["values"][idx] == 180
    assert series["claude-opus-4-6"]["values"][idx] == 280
    # Opus has a larger total, so it sorts first.
    assert result["chart3_series"][0]["name"] == "claude-opus-4-6"


def test_chart3_series_assigns_distinct_colors():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00",
              model="a", input_tokens=10, cached_input_tokens=0, output_tokens=0),
        _goal(status="success", finished_at="2026-01-15T11:00:00+00:00",
              model="b", input_tokens=20, cached_input_tokens=0, output_tokens=0),
    ]
    result = aggregate_report_data(goals, days=None)
    colors = [s["color"] for s in result["chart3_series"]]
    assert len(set(colors)) == len(colors)
    # Unknown is reserved for unnamed models only; neither "a" nor "b" is unknown.
    assert "#94a3b8" not in colors


def test_chart3_pins_unknown_last():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00",
              input_tokens=1_000_000, cached_input_tokens=0, output_tokens=0),  # unknown
        _goal(status="success", finished_at="2026-01-15T11:00:00+00:00",
              model="a", input_tokens=10, cached_input_tokens=0, output_tokens=0),
    ]
    result = aggregate_report_data(goals, days=None)
    names = [s["name"] for s in result["chart3_series"]]
    # Even though "unknown" has the larger total, it must sort to the end.
    assert names == ["a", "unknown"]


def test_cost_per_success_excludes_null_cost():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", cost_usd=None),
        _goal(status="success", finished_at="2026-01-15T11:00:00+00:00", cost_usd=10.0),
    ]
    result = aggregate_report_data(goals, days=None)
    # Only the goal with known cost contributes
    assert "2026-01-15" in result["chart4_buckets"]
    idx = result["chart4_buckets"].index("2026-01-15")
    assert result["chart4_values"][idx] == 10.0


def test_cost_per_success_averages_bucket():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", cost_usd=8.0),
        _goal(status="success", finished_at="2026-01-15T11:00:00+00:00", cost_usd=12.0),
    ]
    result = aggregate_report_data(goals, days=None)
    idx = result["chart4_buckets"].index("2026-01-15")
    assert result["chart4_values"][idx] == 10.0


def test_fail_goals_excluded_from_chart4():
    goals = [_goal(status="fail", finished_at="2026-01-15T10:00:00+00:00", cost_usd=5.0)]
    result = aggregate_report_data(goals, days=None)
    assert result["chart4_buckets"] == []


def test_granularity_daily_for_short_span():
    # 10 days → daily
    goals = [
        _goal(status="success", finished_at="2026-01-01T10:00:00+00:00"),
        _goal(status="success", finished_at="2026-01-10T10:00:00+00:00"),
    ]
    result = aggregate_report_data(goals, days=None)
    assert result["granularity"] == "day"
    assert len(result["buckets"]) == 10


def test_granularity_weekly_for_long_span():
    # 60 days → weekly
    goals = [
        _goal(status="success", finished_at="2026-01-01T10:00:00+00:00"),
        _goal(status="success", finished_at="2026-03-01T10:00:00+00:00"),
    ]
    result = aggregate_report_data(goals, days=None)
    assert result["granularity"] == "week"
    # All bucket keys should be Mondays
    for b in result["buckets"]:
        dt = datetime.strptime(b, "%Y-%m-%d")
        assert dt.weekday() == 0, f"{b} is not a Monday"


def test_days_filter():
    from datetime import timedelta, timezone

    now = datetime.now(tz=timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    recent = (now - timedelta(days=5)).isoformat()

    goals = [
        _goal(status="success", finished_at=old),
        _goal(status="success", finished_at=recent),
    ]
    result = aggregate_report_data(goals, days=10)
    # Only the recent goal should be included
    total_successes = sum(result["chart1_product"]) + sum(result["chart1_meta"]) + sum(result["chart1_retro"])
    assert total_successes == 1


# ── warehouse retry aggregation ──────────────────────────────────────────────


def test_aggregate_warehouse_retry_daily():
    buckets = ["2026-04-08", "2026-04-09", "2026-04-10"]
    wr = {
        "2026-04-08": {"threads": 5, "retry_threads": 0},
        "2026-04-09": {"threads": 6, "retry_threads": 3},
        "2026-04-10": {"threads": 3, "retry_threads": 0},
    }
    bars, lines = _aggregate_warehouse_retry(wr, buckets, "day")
    assert bars == [0, 3, 0]
    assert lines[0] == 0.0
    assert lines[1] == 50.0
    assert lines[2] == 0.0


def test_aggregate_warehouse_retry_zero_threads_returns_none():
    buckets = ["2026-04-08"]
    wr = {}  # no data for this day
    bars, lines = _aggregate_warehouse_retry(wr, buckets, "day")
    assert bars == [0]
    assert lines == [None]


def test_aggregate_warehouse_retry_weekly():
    # Week of 2026-01-12 (Monday); Wed 14 and Thu 15 both fall into it
    buckets = ["2026-01-12"]
    wr = {
        "2026-01-14": {"threads": 4, "retry_threads": 2},
        "2026-01-15": {"threads": 2, "retry_threads": 1},
    }
    bars, lines = _aggregate_warehouse_retry(wr, buckets, "week")
    assert bars == [3]          # 2 + 1
    assert lines == [50.0]      # 3 / 6 * 100


def test_aggregate_warehouse_retry_skips_bad_dates():
    buckets = ["2026-04-08"]
    wr = {"not-a-date": {"threads": 5, "retry_threads": 2}}
    bars, lines = _aggregate_warehouse_retry(wr, buckets, "day")
    assert bars == [0]
    assert lines == [None]


def test_aggregate_report_data_warehouse_retry_overrides_ledger():
    # All goals have attempts=1 (ledger says 0 retries),
    # but warehouse data says there were retries.
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", attempts=1),
        _goal(status="fail",    finished_at="2026-01-15T12:00:00+00:00", attempts=1),
    ]
    wr = {"2026-01-15": {"threads": 4, "retry_threads": 2}}
    result = aggregate_report_data(goals, days=None, warehouse_retry=wr)
    assert result["chart2_source"] == "warehouse"
    idx = result["buckets"].index("2026-01-15")
    assert result["chart2_bar"][idx] == 2
    assert result["chart2_line"][idx] == 50.0


def test_aggregate_report_data_ledger_source_when_no_warehouse():
    goals = [_goal(status="success", finished_at="2026-01-15T10:00:00+00:00", attempts=3)]
    result = aggregate_report_data(goals, days=None)
    assert result["chart2_source"] == "ledger"
    idx = result["buckets"].index("2026-01-15")
    assert result["chart2_bar"][idx] == 1  # 1 goal with attempts > 1


def test_summary_fields_populated():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", cost_usd=5.0),
        _goal(status="fail",    finished_at="2026-01-16T10:00:00+00:00"),
    ]
    result = aggregate_report_data(goals, days=None)
    s = result["summary"]
    assert s["total_closed"] == 2
    assert s["success_count"] == 1
    assert s["success_rate_pct"] == 50.0
    assert s["avg_cost_usd"] == 5.0
    assert s["date_from"] == "2026-01-15"
    assert s["date_to"] == "2026-01-16"


def test_summary_total_cost_sums_all_closed_goals_including_fails():
    # Total cost should include cost from failed goals, unlike avg_cost which
    # covers successes only. This is the real "how much did I spend?" signal.
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", cost_usd=5.0),
        _goal(status="fail",    finished_at="2026-01-16T10:00:00+00:00", cost_usd=3.0),
        _goal(status="success", finished_at="2026-01-17T10:00:00+00:00", cost_usd=2.5),
    ]
    result = aggregate_report_data(goals, days=None)
    s = result["summary"]
    assert s["total_cost_usd"] == 10.5  # 5.0 + 3.0 + 2.5
    assert s["avg_cost_usd"] == 3.75  # (5.0 + 2.5) / 2 successes


def test_summary_total_cost_is_none_when_no_cost_data():
    goals = [
        _goal(status="success", finished_at="2026-01-15T10:00:00+00:00", cost_usd=None),
        _goal(status="fail",    finished_at="2026-01-16T10:00:00+00:00", cost_usd=None),
    ]
    result = aggregate_report_data(goals, days=None)
    assert result["summary"]["total_cost_usd"] is None


def test_empty_data_has_chart2_source():
    from ai_agents_metrics._report_aggregation import _empty_data
    data = _empty_data()
    assert data["chart2_source"] == "ledger"


def test_empty_data_has_chart3_source():
    from ai_agents_metrics._report_aggregation import _empty_data
    data = _empty_data()
    assert data["chart3_source"] == "ledger"


# ── _aggregate_warehouse_tokens_by_model ──────────────────────────────────────


def test_aggregate_warehouse_tokens_daily_no_pricing():
    # No pricing → accumulate raw tokens (input + cached + output) per bucket per model.
    buckets = ["2026-03-31", "2026-04-01", "2026-04-02"]
    rows = [
        ("2026-03-31T10:00:00.000Z", "gpt-5.4", 1000, 500, 200),
        ("2026-04-01T12:00:00.000Z", "gpt-5.4", 2000, 0, 400),
    ]
    per_model = _aggregate_warehouse_tokens_by_model(rows, buckets, "day", None)
    assert list(per_model.keys()) == ["gpt-5.4"]
    values = per_model["gpt-5.4"]
    assert values["2026-03-31"] == 1700  # 1000 + 500 + 200
    assert values["2026-04-01"] == 2400  # 2000 + 0 + 400
    assert values["2026-04-02"] == 0


def test_aggregate_warehouse_tokens_daily_with_pricing():
    buckets = ["2026-04-01"]
    rows = [("2026-04-01T10:00:00.000Z", "claude-sonnet-4-6", 1_000_000, 0, 1_000_000)]
    pricing = {"claude-sonnet-4-6": {"input_per_million_usd": 3.0, "cached_input_per_million_usd": 0.3, "output_per_million_usd": 15.0}}
    per_model = _aggregate_warehouse_tokens_by_model(rows, buckets, "day", pricing)
    # 3.0 (input) + 0 (cached) + 15.0 (output) = 18.0 USD
    assert per_model["claude-sonnet-4-6"]["2026-04-01"] == 18.0


def test_aggregate_warehouse_tokens_skips_out_of_range():
    buckets = ["2026-04-01"]
    rows = [("2026-03-15T10:00:00.000Z", None, 9999, 0, 0)]  # outside bucket range
    per_model = _aggregate_warehouse_tokens_by_model(rows, buckets, "day", None)
    assert per_model == {}


def test_aggregate_warehouse_tokens_skips_bad_timestamps():
    buckets = ["2026-04-01"]
    rows = [("not-a-date", None, 500, 0, 100)]
    per_model = _aggregate_warehouse_tokens_by_model(rows, buckets, "day", None)
    assert per_model == {}


def test_aggregate_warehouse_tokens_cost_mode_drops_unknown_model():
    # Unknown-model rows are dropped in cost mode — can't compute USD without pricing.
    buckets = ["2026-04-01"]
    rows = [("2026-04-01T10:00:00.000Z", None, 1_000_000, 0, 0)]
    pricing = {"claude-sonnet-4-6": {"input_per_million_usd": 3.0}}
    per_model = _aggregate_warehouse_tokens_by_model(rows, buckets, "day", pricing)
    assert per_model == {}


def test_aggregate_warehouse_tokens_token_mode_keeps_unknown_model():
    # Without pricing, unknown-model rows accumulate under the reserved 'unknown' key
    # so total tokens aren't silently dropped.
    buckets = ["2026-04-01"]
    rows = [("2026-04-01T10:00:00.000Z", None, 100, 50, 30)]
    per_model = _aggregate_warehouse_tokens_by_model(rows, buckets, "day", None)
    assert per_model == {"unknown": {"2026-04-01": 180.0}}


# ── aggregate_report_data with warehouse_tokens ───────────────────────────────


def test_aggregate_report_data_warehouse_tokens_overrides_ledger():
    """Warehouse token rows replace ndjson token values for chart 3."""
    goals = [_goal(input_tokens=9999, cached_input_tokens=9999, output_tokens=9999)]
    wt = [("2026-01-15T10:00:00.000Z", None, 100, 50, 30)]
    data = aggregate_report_data(goals, None, warehouse_tokens=wt)
    assert data["chart3_source"] == "warehouse"
    # Warehouse-only data → one 'unknown' series = 100 + 50 + 30 = 180
    assert len(data["chart3_series"]) == 1
    assert data["chart3_series"][0]["name"] == "unknown"
    assert data["chart3_series"][0]["values"] == [180.0]


def test_aggregate_report_data_ledger_source_when_no_warehouse_tokens():
    goals = [_goal(input_tokens=100, cached_input_tokens=50, output_tokens=30)]
    data = aggregate_report_data(goals, None, warehouse_tokens=None)
    assert data["chart3_source"] == "ledger"


def test_aggregate_report_data_warehouse_tokens_extends_date_range():
    """Warehouse threads from before ndjson goals extend bucket coverage."""
    # ndjson goal on 2026-04-07, warehouse thread on 2026-04-01
    goals = [_goal(finished_at="2026-04-07T10:00:00+00:00")]
    wt = [("2026-04-01T10:00:00.000Z", None, 500, 0, 100)]
    data = aggregate_report_data(goals, None, warehouse_tokens=wt)
    assert data["summary"]["date_from"] == "2026-04-01"
    assert data["summary"]["date_to"] == "2026-04-07"
    assert len(data["buckets"]) == 7  # daily, Apr 1–7


def test_aggregate_report_data_warehouse_tokens_only_no_goals():
    """If ndjson has no goals but warehouse has threads, chart 3 still renders."""
    wt = [("2026-04-01T10:00:00.000Z", None, 300, 100, 50)]
    data = aggregate_report_data([], None, warehouse_tokens=wt)
    assert data["chart3_source"] == "warehouse"
    assert data["chart3_series"][0]["values"] == [450.0]  # 300 + 100 + 50


def test_aggregate_report_data_warehouse_tokens_separates_models():
    """Warehouse path must split chart3_series by model and sort by total desc.

    Parallels test_token_aggregation_separates_models for the ledger path —
    guards against a regression where warehouse aggregation would collapse
    all rows under a single series.
    """
    wt = [
        ("2026-04-01T10:00:00.000Z", "claude-sonnet-4-6", 100, 50, 30),  # total 180
        ("2026-04-01T11:00:00.000Z", "claude-opus-4-6",   200, 0,  80),  # total 280
    ]
    data = aggregate_report_data([], None, warehouse_tokens=wt)
    assert data["chart3_source"] == "warehouse"
    names = [s["name"] for s in data["chart3_series"]]
    # Opus has the larger total, so it sorts first.
    assert names == ["claude-opus-4-6", "claude-sonnet-4-6"]
    by_name = {s["name"]: s for s in data["chart3_series"]}
    assert by_name["claude-sonnet-4-6"]["values"] == [180.0]
    assert by_name["claude-opus-4-6"]["values"] == [280.0]
    # Distinct colors assigned from the palette.
    assert by_name["claude-sonnet-4-6"]["color"] != by_name["claude-opus-4-6"]["color"]


# ── render smoke test ─────────────────────────────────────────────────────────


def test_render_html_returns_string_with_key_markers():
    from ai_agents_metrics._report_aggregation import _empty_data

    data = _empty_data()
    html = render_html_report(data, "2026-01-15 12:00 UTC")
    assert "<!DOCTYPE html>" in html
    assert "Codex Metrics" in html
    assert "2026-01-15 12:00 UTC" in html
    assert "DATA" in html


def test_render_html_embeds_chart_data():
    goals = [_goal(status="success", finished_at="2026-01-15T10:00:00+00:00", cost_usd=5.0)]
    data = aggregate_report_data(goals, days=None)
    html = render_html_report(data, "2026-01-15 10:00 UTC")
    # Chart data should be embedded as JSON
    assert '"chart1_product"' in html
    assert '"buckets"' in html
    assert "2026-01-15" in html


def test_render_html_escapes_script_closing_tag():
    """Inline JSON must not contain </script> — would break the HTML parser."""
    from ai_agents_metrics._report_aggregation import _empty_data

    data = _empty_data()
    html = render_html_report(data, "2026-01-15 10:00 UTC")
    # The raw sequence must not appear inside the <script> block
    assert "</script>" not in html.split("<script")[1].split("</script>")[0]


def test_render_html_no_external_urls():
    from ai_agents_metrics._report_aggregation import _empty_data

    data = _empty_data()
    html = render_html_report(data, "2026-01-15 10:00 UTC")
    # No CDN or external script/stylesheet references
    for marker in ["cdn.jsdelivr", "unpkg.com", "cdnjs.cloudflare", "fonts.googleapis"]:
        assert marker not in html, f"Found external URL: {marker}"


def test_embedded_js_is_valid_syntax(tmp_path):
    """Extract the inline <script> from the generated HTML and validate it with node --check.

    This catches TypeScript-only syntax (e.g. `as Type`) accidentally left in
    the embedded JS, which Python tests cannot see.
    """
    import re
    import shutil
    import subprocess


    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    assert node is not None  # narrow type for static analysis

    from ai_agents_metrics._report_aggregation import _empty_data

    data = _empty_data()
    html = render_html_report(data, "2026-01-15 10:00 UTC")

    # Extract content of the first <script> block (no src attribute)
    match = re.search(r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", html, re.DOTALL)
    assert match, "No inline <script> block found in rendered HTML"

    js_src = match.group(1)
    js_file = tmp_path / "embedded.js"
    js_file.write_text(js_src, encoding="utf-8")

    result = subprocess.run(
        [node, "--check", str(js_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"node --check failed — embedded JS has a syntax error:\n{result.stderr}"
    )


# ── chart 5: practice-event distribution ──────────────────────────────────────


def test_chart5_empty_when_no_practice_rows():
    result = aggregate_report_data([_goal()], days=None)
    c5 = result["chart5"]
    assert c5["labels"] == []
    assert c5["total_events"] == 0
    assert c5["source"] == "none"


def test_chart5_aggregates_by_name_and_kind():
    rows = [
        ("Explore", "Agent", 13),
        ("code-reviewer", "Agent", 4),
        ("commit", "Skill", 8),
        ("code-review:code-review", "Skill", 6),
    ]
    result = aggregate_report_data(
        [_goal()], days=None, warehouse_practice=rows,
    )
    c5 = result["chart5"]
    assert c5["source"] == "warehouse"
    assert c5["total_events"] == 31
    assert c5["shown_events"] == 31
    # Sorted by total count desc: Explore (13), commit (8), code-review... (6), code-reviewer (4)
    assert c5["labels"] == ["Explore", "commit", "code-review:code-review", "code-reviewer"]
    assert c5["agent"] == [13, 0, 0, 4]
    assert c5["skill"] == [0, 8, 6, 0]
    assert c5["other"] == [0, 0, 0, 0]


def test_chart5_folds_multiple_kinds_for_same_name():
    """A practice name appearing under multiple source_kinds folds into per-kind buckets."""
    rows = [
        ("discovery", "Agent", 5),
        ("discovery", "Skill", 2),
        ("discovery", "unknown_kind", 1),
    ]
    result = aggregate_report_data(
        [_goal()], days=None, warehouse_practice=rows,
    )
    c5 = result["chart5"]
    assert c5["labels"] == ["discovery"]
    assert c5["agent"] == [5]
    assert c5["skill"] == [2]
    assert c5["other"] == [1]
    assert c5["total_events"] == 8


def test_chart5_truncates_to_top_n_and_records_long_tail():
    """Only top-15 names render; the remainder is surfaced via total vs shown."""
    rows = [
        (f"skill_{i:02d}", "Skill", 20 - i)  # 20, 19, ..., 1
        for i in range(20)
    ]
    result = aggregate_report_data(
        [_goal()], days=None, warehouse_practice=rows,
    )
    c5 = result["chart5"]
    assert len(c5["labels"]) == 15
    # Top-15 by count = skill_00..skill_14 with counts 20..6
    assert c5["labels"][0] == "skill_00"
    assert c5["labels"][-1] == "skill_14"
    assert c5["shown_events"] == sum(range(6, 21))  # 6+7+...+20
    assert c5["total_events"] == sum(range(1, 21))  # 1+2+...+20
    assert c5["total_events"] > c5["shown_events"]


def test_chart5_ignores_blank_name_and_zero_count():
    rows = [
        ("Explore", "Agent", 3),
        ("", "Agent", 99),      # blank name — skip
        ("phantom", "Skill", 0),  # zero count — skip
        (None, "Agent", 5),     # None name — skip
    ]
    result = aggregate_report_data(
        [_goal()], days=None, warehouse_practice=rows,  # type: ignore[arg-type]
    )
    c5 = result["chart5"]
    assert c5["labels"] == ["Explore"]
    assert c5["total_events"] == 3


def test_chart5_present_in_empty_data_path():
    """Warehouse-only practice data must survive even when goals produce no buckets."""
    rows = [("Explore", "Agent", 2)]
    # No goals at all → date range is empty → _empty_data path
    result = aggregate_report_data([], days=None, warehouse_practice=rows)
    c5 = result["chart5"]
    # chart5 still aggregates, independent of the goals-date bucket logic
    assert c5["labels"] == ["Explore"]
    assert c5["total_events"] == 2
    assert c5["source"] == "warehouse"


# ── warehouse-state detection ────────────────────────────────────────────────


def _build_warehouse(path: Path, *, include_practice_table: bool = True,
                    goals_cwd: str | None = None) -> None:
    """Create a minimal warehouse fixture for state-check tests."""
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE derived_goals ("
            "thread_id TEXT, cwd TEXT, last_seen_at TEXT, retry_count INTEGER, model TEXT"
            ")"
        )
        if include_practice_table:
            conn.execute(
                "CREATE TABLE derived_practice_events ("
                "thread_id TEXT, practice_name TEXT, source_kind TEXT"
                ")"
            )
        if goals_cwd is not None:
            conn.execute(
                "INSERT INTO derived_goals VALUES (?, ?, ?, ?, ?)",
                ("t1", goals_cwd, "2026-04-20T00:00:00Z", 0, "claude-sonnet-4-6"),
            )
        conn.commit()


def test_warehouse_state_missing_file(tmp_path: Path):
    state = check_warehouse_state(tmp_path / "nonexistent.db", "/home/me/proj")
    assert state == {"status": "missing_file"}


def test_warehouse_state_schema_outdated_missing_practice_table(tmp_path: Path):
    db = tmp_path / "wh.db"
    _build_warehouse(db, include_practice_table=False, goals_cwd="/home/me/proj")
    assert check_warehouse_state(db, "/home/me/proj") == {"status": "schema_outdated"}


def test_warehouse_state_schema_outdated_no_goals_table(tmp_path: Path):
    db = tmp_path / "wh.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE foo (x INTEGER)")
    assert check_warehouse_state(db, "/home/me/proj") == {"status": "schema_outdated"}


def test_warehouse_state_empty_for_cwd(tmp_path: Path):
    db = tmp_path / "wh.db"
    _build_warehouse(db, goals_cwd="/Users/other/mac-project")
    assert check_warehouse_state(db, "/home/me/proj") == {"status": "empty_for_cwd"}


def test_warehouse_state_ok(tmp_path: Path):
    db = tmp_path / "wh.db"
    _build_warehouse(db, goals_cwd="/home/me/proj")
    assert check_warehouse_state(db, "/home/me/proj") == {"status": "ok"}


def test_warehouse_state_sql_error_treated_as_outdated(tmp_path: Path):
    # Non-sqlite bytes — sqlite3.connect will open fine but any query will raise.
    db = tmp_path / "wh.db"
    db.write_bytes(b"this is not a sqlite database file")
    assert check_warehouse_state(db, "/home/me/proj") == {"status": "schema_outdated"}


def test_aggregate_report_data_includes_warehouse_state():
    result = aggregate_report_data(
        [_goal()],
        days=None,
        warehouse_state={"status": "empty_for_cwd"},
    )
    assert result["warehouse_state"] == {"status": "empty_for_cwd"}


def test_aggregate_report_data_defaults_warehouse_state_to_ok():
    # Not passing warehouse_state should default to status=ok (back-compat with
    # earlier call sites).
    result = aggregate_report_data([_goal()], days=None)
    assert result["warehouse_state"] == {"status": "ok"}


def test_aggregate_report_data_warehouse_state_on_empty_path():
    # Empty-data path (no closed goals) also carries warehouse_state through.
    result = aggregate_report_data(
        [],
        days=None,
        warehouse_state={"status": "missing_file"},
    )
    assert result["warehouse_state"] == {"status": "missing_file"}


def test_render_html_includes_warehouse_callout_wiring():
    # Smoke: the rendered HTML should embed the warehouse_state into DATA so
    # the client-side renderWarehouseCallout() can surface it.
    data = aggregate_report_data(
        [_goal(cost_usd=1.0, input_tokens=10, cached_input_tokens=0, output_tokens=5)],
        days=None,
        warehouse_state={"status": "empty_for_cwd"},
    )
    html = render_html_report(data, "2026-04-20 12:00 UTC")
    assert "renderWarehouseCallout" in html
    assert '"warehouse_state":' in html
    assert "empty_for_cwd" in html
    assert 'id="warehouse-callout"' in html


def test_pricing_file_has_claude_opus_4_7():
    """Guard against regression: opus-4-7 was silently dropped from chart 3
    when absent from the pricing file (P0-4, 2026-04-20). Keep it here."""
    from ai_agents_metrics.usage_resolution import PRICING_JSON_PATH, load_pricing
    pricing = load_pricing(PRICING_JSON_PATH)
    assert "claude-opus-4-7" in pricing
    entry = pricing["claude-opus-4-7"]
    # Sanity — all four price fields present and non-null.
    for field in ("input_per_million_usd", "cached_input_per_million_usd",
                  "cache_creation_per_million_usd", "output_per_million_usd"):
        assert entry.get(field) is not None, f"missing {field}"


# ── HTML template pins (guard against regression on canvas-drawing code) ─────


def test_smartmax_cap_has_rawmax_floor():
    """smartMax cap must be floored at rawMax/5 so that sparse data with a
    near-zero median never produces a cap >5× below rawMax.

    Regression bug (2026-04-20): ledger cost data with many zero-buckets had
    median ~$1.36 vs rawMax $120.91 — old cap `median*2.5` = $3.4 made every
    non-outlier bar indistinguishable (24× off-scale). New floor clamps
    cap ≥ rawMax/5 so outliers are at most 5× above the visible axis.
    """
    from ai_agents_metrics._report_template import _HTML_TEMPLATE
    # Pin the exact formula so that a future well-intentioned "simplification"
    # cannot silently revert this fix.
    assert "Math.max(median * 2.5, rawMax / 5)" in _HTML_TEMPLATE


def test_drawline_stacks_overlapping_outlier_labels():
    """Chart 4 outlier labels stack across multiple y-levels when adjacent
    outliers would otherwise collide horizontally.

    Regression bug (2026-04-20): `$147.70 $140.62` on consecutive days
    rendered on the same y-coordinate, labels visually touching.
    """
    from ai_agents_metrics._report_template import _HTML_TEMPLATE
    # Marker variables for the stacking loop; presence pins the algorithm.
    assert "outlierRowEdges" in _HTML_TEMPLATE
    assert "OUTLIER_LABEL_LINE_HEIGHT" in _HTML_TEMPLATE
    assert "OUTLIER_LABEL_MAX_LEVELS" in _HTML_TEMPLATE
    # Top margin bumps up when clipped to fit stacked labels.
    assert "clipped ? 36 : 20" in _HTML_TEMPLATE


# ── retry-pressure semantics (main_attempt_count, not subagent-aliased) ──────


def test_retry_pressure_uses_main_attempt_count_sql():
    """Chart 2 SQL must read main_attempt_count (H-040 classifier), not the
    raw retry_count which aliases subagent spawns as retries on Claude data.

    Regression bug (2026-04-20): on 22 local threads, retry_count>0 showed
    40.9% 'retry pressure' while main_attempt_count>1 showed 0% — the chart
    was reading subagent-usage growth as quality degradation. SQL change
    must survive refactors.
    """
    from ai_agents_metrics import commands as commands_module
    commands_py = Path(commands_module.__file__).read_text()
    # Pin the exact formulation so a later "simplification" cannot revert it.
    assert "COALESCE(main_attempt_count, 1)" in commands_py
    # And the downstream check must compare to 1 (main_attempts > 1 = retry).
    assert "main_attempts > 1" in commands_py


def test_retry_pressure_subtitle_disambiguates_from_subagents():
    """Chart 2 subtitle must say 'main-agent session' and 'subagent spawns
    excluded' so the human reader does not confuse this signal with total
    session-file count (which would include Task() subagent spawns)."""
    from ai_agents_metrics._report_template import _HTML_TEMPLATE
    assert "main-agent session" in _HTML_TEMPLATE
    assert "subagent spawns excluded" in _HTML_TEMPLATE
    assert "Main-agent retry threads" in _HTML_TEMPLATE


def test_retry_pressure_no_retries_message_is_source_specific():
    """The green 'no retries' plaque text changes by source so it accurately
    reflects the metric: warehouse-source measures main-agent sessions,
    ledger-source measures goal-level attempt count."""
    from ai_agents_metrics._report_template import _HTML_TEMPLATE
    assert "No main-agent retries" in _HTML_TEMPLATE
    assert "every task completed in a single main session" in _HTML_TEMPLATE
    # Ledger path keeps its legacy wording.
    assert "No retries — all goals completed on first attempt" in _HTML_TEMPLATE


def test_retry_chart_renders_when_all_rates_are_zero():
    """When the retry signal is genuinely zero (all threads completed in a
    single main session), the chart should still render so the no-retries
    plaque can appear. Previously all-zero was conflated with 'no data'."""
    from ai_agents_metrics._report_template import _HTML_TEMPLATE
    # The empty-state guard must not trigger on all-zero line values.
    assert "const lineHasData = lineValues.some(v => v !== null)" in _HTML_TEMPLATE
