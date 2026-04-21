"""Chart-data aggregation for the HTML report.

Transforms raw goals (from the ndjson ledger) and optional warehouse rows
into the flat ``dict`` consumed by :func:`render_html_report`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ._report_buckets import _bucket_key, _make_buckets, _parse_date

# ── internal helpers ──────────────────────────────────────────────────────────


def _avg_or_none(lst: list[int]) -> float | None:
    return round(sum(lst) / len(lst), 2) if lst else None


def _apply_token_pricing(
    inp: int,
    cac: int,
    out: int,
    model: str | None,
    pricing: dict[str, dict[str, float | None]] | None,
) -> tuple[float, float, float] | None:
    """Convert raw token counts to USD using *pricing*, or return raw counts.

    Three outcomes:
    - pricing present AND model has an entry → return cost tuple (USD)
    - pricing present BUT model has no entry → return ``None`` (skip row)
    - pricing is ``None`` → return raw token counts as floats

    Skipping unknown models prevents raw token counts from being silently
    rendered as dollar amounts on a cost-mode chart.
    """
    if pricing is not None:
        p = pricing.get(model or "") if model else None
        if not p:
            return None  # model unknown — skip rather than corrupt the chart
        return (
            round(inp * (p.get("input_per_million_usd") or 0.0) / 1_000_000, 6),
            round(cac * (p.get("cached_input_per_million_usd") or 0.0) / 1_000_000, 6),
            round(out * (p.get("output_per_million_usd") or 0.0) / 1_000_000, 6),
        )
    # No pricing at all — accumulate raw token counts.
    return float(inp), float(cac), float(out)


# ── model-series color palette ────────────────────────────────────────────────

# Deterministic palette used when stacking chart-3 by model.
# Models are assigned colors in sorted order so the same model always gets the
# same color across runs and across charts.
_MODEL_COLOR_PALETTE: tuple[str, ...] = (
    "#3b82f6",  # blue
    "#8b5cf6",  # purple
    "#10b981",  # green
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#14b8a6",  # teal
    "#f97316",  # orange
    "#ec4899",  # pink
)
_MODEL_UNKNOWN_COLOR = "#94a3b8"  # slate
_MODEL_UNKNOWN_LABEL = "unknown"


def _assign_model_colors(models: list[str]) -> dict[str, str]:
    """Assign a stable color per model name; 'unknown' always gets slate."""
    known = sorted(m for m in models if m != _MODEL_UNKNOWN_LABEL)
    colors = {m: _MODEL_COLOR_PALETTE[i % len(_MODEL_COLOR_PALETTE)] for i, m in enumerate(known)}
    if _MODEL_UNKNOWN_LABEL in models:
        colors[_MODEL_UNKNOWN_LABEL] = _MODEL_UNKNOWN_COLOR
    return colors


def _build_chart3_series(
    per_model: dict[str, dict[str, float]],
    buckets: list[str],
) -> list[dict[str, Any]]:
    """Turn a {model → bucket → value} map into chart-3 series, sorted by total desc.

    Known models come first (highest total first); 'unknown' is always pinned last.
    """
    totals = {m: sum(vals.values()) for m, vals in per_model.items()}
    known = sorted(
        (m for m in per_model if m != _MODEL_UNKNOWN_LABEL),
        key=lambda m: (-totals[m], m),
    )
    order = known + ([_MODEL_UNKNOWN_LABEL] if _MODEL_UNKNOWN_LABEL in per_model else [])
    colors = _assign_model_colors(list(per_model.keys()))
    return [
        {
            "name": m,
            "values": [round(per_model[m].get(b, 0.0), 4) for b in buckets],
            "color": colors[m],
        }
        for m in order
    ]


# ── practice-event kinds for chart 5 ─────────────────────────────────────────

# Limit chart 5 to the top N most-frequent practice names to keep the bar chart
# readable. A long-tail count is surfaced in the summary line.
_CHART5_TOP_N = 15

# Source-kind normalization: raw values from derive_classify map into three
# display buckets. Agents (subagent spawns) carry the main compression signal;
# Skills are scripted workflows; everything else falls into "other" so we never
# silently drop rows.
_CHART5_AGENT_KINDS = frozenset({"Agent", "agent", "agent_spawn", "subagent"})
_CHART5_SKILL_KINDS = frozenset({"Skill", "skill", "skill_invocation"})


def _chart5_kind_bucket(source_kind: str) -> str:
    """Map a raw ``source_kind`` to one of ``agent`` / ``skill`` / ``other``."""
    if source_kind in _CHART5_AGENT_KINDS:
        return "agent"
    if source_kind in _CHART5_SKILL_KINDS:
        return "skill"
    return "other"


def _aggregate_practice_distribution(
    rows: list[tuple[str, str, int]] | None,
) -> dict[str, Any]:
    """Aggregate ``(practice_name, source_kind, count)`` into chart-5 series.

    Returns a dict with:
    - ``labels`` — top-N practice names, sorted by total count desc
    - ``agent`` / ``skill`` / ``other`` — per-label counts for each kind bucket
    - ``total_events`` — total practice events across *all* names
    - ``shown_events`` — total events represented by the shown top-N bars
    - ``source`` — ``"warehouse"`` when rows were provided, ``"none"`` otherwise

    The three-bucket stack keeps the chart honest when derive_classify emits
    kinds we don't yet recognize — they land in ``other`` rather than being
    silently dropped.
    """
    if not rows:
        return _empty_practice_chart()

    # Fold (name, kind) pairs into per-name buckets. Inputs may arrive with
    # multiple rows per name if the warehouse distinguishes kinds in its
    # GROUP BY; this layer is robust to that either way.
    per_name: dict[str, dict[str, int]] = {}
    total_events = 0
    for practice_name, source_kind, count in rows:
        if not practice_name or count <= 0:
            continue
        bucket = _chart5_kind_bucket(source_kind or "")
        entry = per_name.setdefault(practice_name, {"agent": 0, "skill": 0, "other": 0})
        entry[bucket] += count
        total_events += count

    if not per_name:
        return _empty_practice_chart()

    # Order by total count desc, break ties alphabetically for determinism.
    ordered = sorted(
        per_name.items(),
        key=lambda kv: (-(kv[1]["agent"] + kv[1]["skill"] + kv[1]["other"]), kv[0]),
    )
    top = ordered[:_CHART5_TOP_N]

    labels = [name for name, _ in top]
    agent = [vals["agent"] for _, vals in top]
    skill = [vals["skill"] for _, vals in top]
    other = [vals["other"] for _, vals in top]
    shown_events = sum(agent) + sum(skill) + sum(other)

    return {
        "labels": labels,
        "agent": agent,
        "skill": skill,
        "other": other,
        "total_events": total_events,
        "shown_events": shown_events,
        "source": "warehouse",
    }


def _empty_practice_chart() -> dict[str, Any]:
    """Return the chart-5 shape used when no practice-event rows are available."""
    return {
        "labels": [],
        "agent": [],
        "skill": [],
        "other": [],
        "total_events": 0,
        "shown_events": 0,
        "source": "none",
    }


# ── warehouse-level aggregators ───────────────────────────────────────────────


def _aggregate_warehouse_tokens_by_model(
    rows: list[tuple[str, str | None, int, int, int]],
    buckets: list[str],
    gran: str,
    pricing: dict[str, dict[str, float | None]] | None,
) -> dict[str, dict[str, float]]:
    """Map per-thread warehouse token data into {model → bucket → total value}.

    In cost mode (pricing present), rows for unknown models are dropped (we
    can't compute USD). In token mode, unknown-model rows accumulate under
    the reserved ``'unknown'`` key so nothing is silently lost.
    """
    bucket_set = set(buckets)
    per_model: dict[str, dict[str, float]] = {}

    for ts, model, inp, cac, out in rows:
        dt = _parse_date(ts)
        if dt is None:
            continue
        bk = _bucket_key(dt, gran)
        if bk not in bucket_set:
            continue
        applied = _apply_token_pricing(inp, cac, out, model, pricing)
        if applied is None:
            continue  # cost mode + unknown model → skip
        key = (model or "").strip() or _MODEL_UNKNOWN_LABEL
        per_model.setdefault(key, dict.fromkeys(buckets, 0.0))[bk] += sum(applied)

    return per_model


def _aggregate_warehouse_retry(
    warehouse_retry: dict[str, dict[str, int]],
    buckets: list[str],
    gran: str,
) -> tuple[list[int], list[float | None]]:
    """Map per-day warehouse retry data into chart buckets.

    Returns *(bar_values, line_values)* where *bar* is retry_threads per
    bucket and *line* is retry_rate % (0-100) per bucket, or ``None`` when
    there are no threads in that bucket.
    """
    bucket_threads: dict[str, int] = {b: 0 for b in buckets}
    bucket_retries: dict[str, int] = {b: 0 for b in buckets}
    bucket_set = set(buckets)

    for date_str, vals in warehouse_retry.items():
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        bk = _bucket_key(dt, gran)
        if bk in bucket_set:
            bucket_threads[bk] += vals.get("threads", 0)
            bucket_retries[bk] += vals.get("retry_threads", 0)

    bars = [bucket_retries[b] for b in buckets]
    lines: list[float | None] = [
        round(bucket_retries[b] / bucket_threads[b] * 100, 1) if bucket_threads[b] else None
        for b in buckets
    ]
    return bars, lines


# ── goal-series accumulator ───────────────────────────────────────────────────


@dataclass
class _GoalSeries:  # pylint: disable=too-many-instance-attributes
    """Mutable accumulator for per-bucket goal series data."""
    c1_product: dict[str, int]
    c1_meta: dict[str, int]
    c1_retro: dict[str, int]
    c2_retry: dict[str, int]
    c2_attempts: dict[str, list[int]]
    c3_by_model: dict[str, dict[str, float]]
    c4: dict[str, list[float]] = field(default_factory=dict)
    success_count: int = 0
    known_cost_successes: list[float] = field(default_factory=list)
    total_known_cost_usd: float = 0.0


def _empty_goal_series(buckets: list[str]) -> _GoalSeries:
    z_int = dict.fromkeys(buckets, 0)
    return _GoalSeries(
        c1_product=z_int.copy(),
        c1_meta=z_int.copy(),
        c1_retro=z_int.copy(),
        c2_retry=z_int.copy(),
        c2_attempts={b: [] for b in buckets},
        c3_by_model={},
    )


# ── aggregation phases ────────────────────────────────────────────────────────


def _filter_closed_goals(goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only goals with a closed status and a non-null finished_at."""
    closed_statuses = {"success", "fail"}
    return [g for g in goals if g.get("status") in closed_statuses and g.get("finished_at")]


def _apply_date_cutoff(
    closed: list[dict[str, Any]],
    days: int,
    warehouse_tokens: list[tuple[str, str | None, int, int, int]] | None,
) -> tuple[list[dict[str, Any]], list[tuple[str, str | None, int, int, int]] | None]:
    """Drop goals and warehouse token rows older than *days* days."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    filtered_closed = [
        g for g in closed if (_parse_date(g["finished_at"]) or epoch) >= cutoff
    ]
    filtered_tokens = (
        None if warehouse_tokens is None
        else [row for row in warehouse_tokens if (dt := _parse_date(row[0])) is not None and dt >= cutoff]
    )
    return filtered_closed, filtered_tokens


def _parse_closed_goals(
    closed: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], datetime]]:
    """Parse ``finished_at`` for each closed goal; drop rows with unparseable dates."""
    return [(g, dt) for g in closed if (dt := _parse_date(g["finished_at"])) is not None]


def _collect_chart_dates(
    parsed: list[tuple[dict[str, Any], datetime]],
    warehouse_tokens: list[tuple[str, str | None, int, int, int]] | None,
) -> list[datetime]:
    """Collect all datetimes that determine the chart date range."""
    dates: list[datetime] = [dt for _, dt in parsed]
    if warehouse_tokens:
        for row in warehouse_tokens:
            dt = _parse_date(row[0])
            if dt is not None:
                dates.append(dt)
    return dates


def _determine_granularity(dates: list[datetime]) -> "_AggregationAxis":
    """Pick daily vs weekly granularity and build the bucket list."""
    earliest, latest = min(dates), max(dates)
    gran = "day" if (latest - earliest).days <= 30 else "week"
    return _AggregationAxis(
        buckets=_make_buckets(earliest, latest, gran),
        gran=gran,
        earliest=earliest,
        latest=latest,
    )


def _parse_goal_scalars(
    g: dict[str, Any],
) -> tuple[str | None, int, str, str | None, int, int, int]:
    """Extract and normalise the scalar fields used for series accumulation."""
    status = g.get("status")
    attempts = max(1, int(g.get("attempts") or 1))
    gtype = g.get("goal_type") or "meta"
    model = (g.get("model") or "").strip() or None
    inp_tok = int(g.get("input_tokens") or 0)
    cac_tok = int(g.get("cached_input_tokens") or 0)
    out_tok = int(g.get("output_tokens") or 0)
    return status, attempts, gtype, model, inp_tok, cac_tok, out_tok


def _update_success_type_counts(series: _GoalSeries, gtype: str, bk: str) -> None:
    """Increment the appropriate chart-1 success counter for *gtype*."""
    if gtype == "product":
        series.c1_product[bk] += 1
    elif gtype == "retro":
        series.c1_retro[bk] += 1
    else:
        series.c1_meta[bk] += 1


def _accumulate_goals(
    parsed: list[tuple[dict[str, Any], datetime]],
    buckets: list[str],
    gran: str,
    pricing: dict[str, dict[str, float | None]] | None,
) -> _GoalSeries:
    """Iterate closed goals and fill per-bucket series accumulators."""
    bucket_set = set(buckets)
    series = _empty_goal_series(buckets)

    for g, dt in parsed:
        bk = _bucket_key(dt, gran)
        if bk not in bucket_set:
            continue

        status, attempts, gtype, model, inp_tok, cac_tok, out_tok = _parse_goal_scalars(g)

        if status == "success":
            series.success_count += 1
            _update_success_type_counts(series, gtype, bk)

        series.c2_attempts[bk].append(attempts)
        if attempts > 1:
            series.c2_retry[bk] += 1

        applied = _apply_token_pricing(inp_tok, cac_tok, out_tok, model, pricing)
        if applied is not None:
            key = model or _MODEL_UNKNOWN_LABEL
            series.c3_by_model.setdefault(key, dict.fromkeys(buckets, 0.0))[bk] += sum(applied)

        if g.get("cost_usd") is not None:
            cost = float(g["cost_usd"])
            series.total_known_cost_usd += cost
            if status == "success":
                series.c4.setdefault(bk, []).append(cost)
                series.known_cost_successes.append(cost)

    return series


@dataclass(frozen=True)
class _C4Series:
    pairs: list[tuple[str, float]]
    buckets: list[str]
    values: list[float]


def _compute_c4_series(series: _GoalSeries) -> _C4Series:
    """Compute chart-4 (cost-per-success) bucket averages."""
    pairs = [(b, sum(v) / len(v)) for b, v in series.c4.items() if v]
    return _C4Series(
        pairs=pairs,
        buckets=[p[0] for p in pairs],
        values=[round(p[1], 4) for p in pairs],
    )


def _compute_cost_trend(pairs: list[tuple[str, float]]) -> str | None:
    """Compare second-half average to first-half average of cost-per-success pairs."""
    if len(pairs) < 4:
        return None
    mid = len(pairs) // 2
    first_avg = sum(v for _, v in pairs[:mid]) / mid
    second_avg = sum(v for _, v in pairs[mid:]) / (len(pairs) - mid)
    ratio = second_avg / first_avg if first_avg > 0 else 1.0
    if ratio < 0.85:
        return "improving"
    if ratio > 1.15:
        return "worsening"
    return "stable"


def _build_chart1(
    series: _GoalSeries,
    buckets: list[str],
) -> tuple[list[int], list[int], list[int]]:
    """Extract chart-1 (successes by type) lists from the series accumulator."""
    return (
        [series.c1_product[b] for b in buckets],
        [series.c1_meta[b] for b in buckets],
        [series.c1_retro[b] for b in buckets],
    )


def _build_chart2(
    warehouse_retry: dict[str, dict[str, int]] | None,
    series: _GoalSeries,
    buckets: list[str],
    gran: str,
) -> tuple[list[int], list[float | None], str]:
    """Return chart-2 (retry pressure) series and its data source label."""
    if warehouse_retry is not None:
        bar_vals, line_vals = _aggregate_warehouse_retry(warehouse_retry, buckets, gran)
        return bar_vals, line_vals, "warehouse"
    return (
        [series.c2_retry[b] for b in buckets],
        [_avg_or_none(series.c2_attempts[b]) for b in buckets],
        "ledger",
    )


def _build_chart3(
    warehouse_tokens: list[tuple[str, str | None, int, int, int]] | None,
    series: _GoalSeries,
    buckets: list[str],
    gran: str,
    pricing: dict[str, dict[str, float | None]] | None,
) -> tuple[list[dict[str, Any]], str]:
    """Return chart-3 (token/cost usage) series (stacked by model) and its source label."""
    if warehouse_tokens:
        per_model = _aggregate_warehouse_tokens_by_model(warehouse_tokens, buckets, gran, pricing)
        return _build_chart3_series(per_model, buckets), "warehouse"
    return _build_chart3_series(series.c3_by_model, buckets), "ledger"


def _compute_ledger_date_range(
    parsed: list[tuple[dict[str, Any], datetime]],
) -> tuple[str | None, str | None]:
    """Return (from, to) date strings derived from the ledger goals."""
    dates = [dt for _, dt in parsed]
    if not dates:
        return None, None
    return min(dates).strftime("%Y-%m-%d"), max(dates).strftime("%Y-%m-%d")


def _avg_cost_usd(known_costs: list[float]) -> float | None:
    return round(sum(known_costs) / len(known_costs), 2) if known_costs else None


# ── main aggregation entry point ──────────────────────────────────────────────


@dataclass(frozen=True)
class _AggregationAxis:
    buckets: list[str]
    gran: str
    earliest: datetime
    latest: datetime


@dataclass(frozen=True)
class _ChartOutputs:
    chart1: tuple[list[int], list[int], list[int]]
    chart2: tuple[list[int], list[float | None], str]
    chart3: tuple[list[dict[str, Any]], str]
    chart5: dict[str, Any]


def _assemble_report_dict(
    *,
    parsed: list[tuple[dict[str, Any], datetime]],
    axis: _AggregationAxis,
    series: Any,
    c4: Any,
    charts: _ChartOutputs,
    state: dict[str, str],
    pricing: dict[str, dict[str, float | None]] | None,
) -> dict[str, Any]:
    ledger_date_from, ledger_date_to = _compute_ledger_date_range(parsed)
    total = len(parsed)
    return {
        "granularity": axis.gran,
        "buckets": axis.buckets,
        "chart1_product": charts.chart1[0],
        "chart1_meta": charts.chart1[1],
        "chart1_retro": charts.chart1[2],
        "chart2_bar": charts.chart2[0],
        "chart2_line": charts.chart2[1],
        "chart2_source": charts.chart2[2],
        "chart3_mode": "cost" if pricing else "tokens",
        "chart3_source": charts.chart3[1],
        "chart3_series": charts.chart3[0],
        "chart4_buckets": c4.buckets,
        "chart4_values": c4.values,
        "chart5": charts.chart5,
        "ledger_date_from": ledger_date_from,
        "ledger_date_to": ledger_date_to,
        "history_date_from": axis.earliest.strftime("%Y-%m-%d"),
        "history_date_to": axis.latest.strftime("%Y-%m-%d"),
        "warehouse_state": state,
        "summary": {
            "total_closed": total,
            "success_count": series.success_count,
            "success_rate_pct": round(100 * series.success_count / total, 1) if total else None,
            "total_cost_usd": round(series.total_known_cost_usd, 2) if series.total_known_cost_usd else None,
            "avg_cost_usd": _avg_cost_usd(series.known_cost_successes),
            "cost_trend": _compute_cost_trend(c4.pairs),
            "date_from": axis.earliest.strftime("%Y-%m-%d"),
            "date_to": axis.latest.strftime("%Y-%m-%d"),
        },
    }


def aggregate_report_data(
    goals: list[dict[str, Any]],
    days: int | None,
    warehouse_retry: dict[str, dict[str, int]] | None = None,
    warehouse_tokens: list[tuple[str, str | None, int, int, int]] | None = None,
    pricing: dict[str, dict[str, float | None]] | None = None,
    warehouse_practice: list[tuple[str, str, int]] | None = None,
    warehouse_state: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Bucket closed goals into chart-ready series.

    Returns a dict consumed by :func:`render_html_report`.
    """
    closed = _filter_closed_goals(goals)

    if days is not None:
        closed, warehouse_tokens = _apply_date_cutoff(closed, days, warehouse_tokens)

    parsed = _parse_closed_goals(closed)
    dates = _collect_chart_dates(parsed, warehouse_tokens)

    chart5 = _aggregate_practice_distribution(warehouse_practice)
    state = warehouse_state or {"status": "ok"}

    if not dates:
        empty = _empty_data()
        empty["chart5"] = chart5
        empty["warehouse_state"] = state
        return empty

    axis = _determine_granularity(dates)
    series = _accumulate_goals(parsed, axis.buckets, axis.gran, pricing)
    c4 = _compute_c4_series(series)
    charts = _ChartOutputs(
        chart1=_build_chart1(series, axis.buckets),
        chart2=_build_chart2(warehouse_retry, series, axis.buckets, axis.gran),
        chart3=_build_chart3(warehouse_tokens, series, axis.buckets, axis.gran, pricing),
        chart5=chart5,
    )

    return _assemble_report_dict(
        parsed=parsed,
        axis=axis,
        series=series,
        c4=c4,
        charts=charts,
        state=state,
        pricing=pricing,
    )


def _empty_data() -> dict[str, Any]:
    return {
        "granularity": "day",
        "buckets": [],
        "chart1_product": [],
        "chart1_meta": [],
        "chart1_retro": [],
        "chart2_bar": [],
        "chart2_line": [],
        "chart2_source": "ledger",
        "chart3_mode": "tokens",
        "chart3_source": "ledger",
        "chart3_series": [],
        "chart4_buckets": [],
        "chart4_values": [],
        "chart5": _empty_practice_chart(),
        "ledger_date_from": None,
        "ledger_date_to": None,
        "history_date_from": None,
        "history_date_to": None,
        "warehouse_state": {"status": "ok"},
        "summary": None,
    }
