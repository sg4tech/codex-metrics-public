"""Chart-data aggregation for the HTML report.

Transforms raw goals (from the ndjson ledger) and optional warehouse rows
into the flat ``dict`` consumed by :func:`render_html_report`.
"""
from __future__ import annotations

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


# ── warehouse-level aggregators ───────────────────────────────────────────────


def _aggregate_warehouse_tokens(
    rows: list[tuple[str, str | None, int, int, int]],
    buckets: list[str],
    gran: str,
    pricing: dict[str, dict[str, float | None]] | None,
) -> tuple[list[float], list[float], list[float]]:
    """Map per-thread warehouse token data into chart buckets.

    Returns *(inp_vals, cac_vals, out_vals)* indexed by bucket position.
    Uses *pricing* to compute cost values when pricing is available.
    """
    bucket_set = set(buckets)
    c3_inp: dict[str, float] = {b: 0.0 for b in buckets}
    c3_cac: dict[str, float] = {b: 0.0 for b in buckets}
    c3_out: dict[str, float] = {b: 0.0 for b in buckets}

    for ts, model, inp, cac, out in rows:
        dt = _parse_date(ts)
        if dt is None:
            continue
        bk = _bucket_key(dt, gran)
        if bk not in bucket_set:
            continue
        applied = _apply_token_pricing(inp, cac, out, model, pricing)
        if applied is None:
            continue
        c3_inp[bk] += applied[0]
        c3_cac[bk] += applied[1]
        c3_out[bk] += applied[2]

    return (
        [round(c3_inp[b], 4) for b in buckets],
        [round(c3_cac[b], 4) for b in buckets],
        [round(c3_out[b], 4) for b in buckets],
    )


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


# ── main aggregation entry point ──────────────────────────────────────────────


def aggregate_report_data(
    goals: list[dict[str, Any]],
    days: int | None,
    warehouse_retry: dict[str, dict[str, int]] | None = None,
    warehouse_tokens: list[tuple[str, str | None, int, int, int]] | None = None,
    pricing: dict[str, dict[str, float | None]] | None = None,
) -> dict[str, Any]:
    """Bucket closed goals into chart-ready series.

    Returns a dict consumed by :func:`render_html_report`.
    """
    closed_statuses = {"success", "fail"}
    closed = [g for g in goals if g.get("status") in closed_statuses and g.get("finished_at")]

    if days is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        closed = [
            g for g in closed
            if (_parse_date(g["finished_at"]) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
        ]
        if warehouse_tokens is not None:
            warehouse_tokens = [
                row for row in warehouse_tokens
                if (dt := _parse_date(row[0])) is not None and dt >= cutoff
            ]

    parsed: list[tuple[dict[str, Any], datetime]] = [
        (g, dt) for g in closed if (dt := _parse_date(g["finished_at"])) is not None
    ]

    # Determine date range from ndjson goals and/or warehouse token threads.
    dates: list[datetime] = [dt for _, dt in parsed]
    if warehouse_tokens:
        for row in warehouse_tokens:
            dt = _parse_date(row[0])
            if dt is not None:
                dates.append(dt)

    if not dates:
        return _empty_data()

    earliest, latest = min(dates), max(dates)
    span_days = (latest - earliest).days
    gran = "day" if span_days <= 30 else "week"

    buckets = _make_buckets(earliest, latest, gran)
    bucket_set = set(buckets)

    c1_product: dict[str, int] = {b: 0 for b in buckets}
    c1_meta: dict[str, int] = {b: 0 for b in buckets}
    c1_retro: dict[str, int] = {b: 0 for b in buckets}
    c2_retry: dict[str, int] = {b: 0 for b in buckets}
    c2_attempts: dict[str, list[int]] = {b: [] for b in buckets}
    c3_inp: dict[str, float] = {b: 0.0 for b in buckets}
    c3_cac: dict[str, float] = {b: 0.0 for b in buckets}
    c3_out: dict[str, float] = {b: 0.0 for b in buckets}
    c4: dict[str, list[float]] = {}

    success_count = 0
    known_cost_successes: list[float] = []

    for g, dt in parsed:
        bk = _bucket_key(dt, gran)
        if bk not in bucket_set:
            continue

        status = g.get("status")
        attempts = max(1, int(g.get("attempts") or 1))
        gtype = g.get("goal_type") or "meta"

        if status == "success":
            success_count += 1
            if gtype == "product":
                c1_product[bk] += 1
            elif gtype == "retro":
                c1_retro[bk] += 1
            else:
                c1_meta[bk] += 1

        c2_attempts[bk].append(attempts)
        if attempts > 1:
            c2_retry[bk] += 1

        inp_tok = int(g.get("input_tokens") or 0)
        cac_tok = int(g.get("cached_input_tokens") or 0)
        out_tok = int(g.get("output_tokens") or 0)
        model = (g.get("model") or "").strip() or None
        applied = _apply_token_pricing(inp_tok, cac_tok, out_tok, model, pricing)
        if applied is not None:
            c3_inp[bk] += applied[0]
            c3_cac[bk] += applied[1]
            c3_out[bk] += applied[2]

        if status == "success" and g.get("cost_usd") is not None:
            cost = float(g["cost_usd"])
            c4.setdefault(bk, []).append(cost)
            known_cost_successes.append(cost)

    c4_pairs = [(b, sum(v) / len(v)) for b, v in c4.items() if v]

    if warehouse_retry is not None:
        chart2_bar_vals, chart2_line_vals = _aggregate_warehouse_retry(warehouse_retry, buckets, gran)
        chart2_source = "warehouse"
    else:
        chart2_bar_vals = [c2_retry[b] for b in buckets]
        chart2_line_vals = [_avg_or_none(c2_attempts[b]) for b in buckets]
        chart2_source = "ledger"

    if warehouse_tokens:
        chart3_inp_vals, chart3_cac_vals, chart3_out_vals = _aggregate_warehouse_tokens(
            warehouse_tokens, buckets, gran, pricing
        )
        chart3_source = "warehouse"
    else:
        chart3_inp_vals = [round(c3_inp[b], 4) for b in buckets]
        chart3_cac_vals = [round(c3_cac[b], 4) for b in buckets]
        chart3_out_vals = [round(c3_out[b], 4) for b in buckets]
        chart3_source = "ledger"

    # Cost trend: compare second half of chart4 to first half.
    cost_trend: str | None = None
    if len(c4_pairs) >= 4:
        mid = len(c4_pairs) // 2
        first_avg = sum(v for _, v in c4_pairs[:mid]) / mid
        second_avg = sum(v for _, v in c4_pairs[mid:]) / (len(c4_pairs) - mid)
        ratio = second_avg / first_avg if first_avg > 0 else 1.0
        cost_trend = "improving" if ratio < 0.85 else ("worsening" if ratio > 1.15 else "stable")

    avg_cost_usd = (
        round(sum(known_cost_successes) / len(known_cost_successes), 2)
        if known_cost_successes else None
    )
    total = len(parsed)

    ledger_dates = [dt for _, dt in parsed]
    ledger_date_from = min(ledger_dates).strftime("%Y-%m-%d") if ledger_dates else None
    ledger_date_to = max(ledger_dates).strftime("%Y-%m-%d") if ledger_dates else None

    return {
        "granularity": gran,
        "buckets": buckets,
        "chart1_product": [c1_product[b] for b in buckets],
        "chart1_meta": [c1_meta[b] for b in buckets],
        "chart1_retro": [c1_retro[b] for b in buckets],
        "chart2_bar": chart2_bar_vals,
        "chart2_line": chart2_line_vals,
        "chart2_source": chart2_source,
        "chart3_mode": "cost" if pricing else "tokens",
        "chart3_source": chart3_source,
        "chart3_input": chart3_inp_vals,
        "chart3_cached": chart3_cac_vals,
        "chart3_output": chart3_out_vals,
        "chart4_buckets": [p[0] for p in c4_pairs],
        "chart4_values": [round(p[1], 4) for p in c4_pairs],
        "ledger_date_from": ledger_date_from,
        "ledger_date_to": ledger_date_to,
        "history_date_from": earliest.strftime("%Y-%m-%d"),
        "history_date_to": latest.strftime("%Y-%m-%d"),
        "summary": {
            "total_closed": total,
            "success_count": success_count,
            "success_rate_pct": round(100 * success_count / total, 1) if total else None,
            "avg_cost_usd": avg_cost_usd,
            "cost_trend": cost_trend,
            "date_from": earliest.strftime("%Y-%m-%d"),
            "date_to": latest.strftime("%Y-%m-%d"),
        },
    }


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
        "chart3_input": [],
        "chart3_cached": [],
        "chart3_output": [],
        "chart4_buckets": [],
        "chart4_values": [],
        "ledger_date_from": None,
        "ledger_date_to": None,
        "history_date_from": None,
        "history_date_to": None,
        "summary": None,
    }
