"""Generate a self-contained HTML report with four trend charts.

All chart rendering happens in the browser via embedded vanilla JS / Canvas 2D.
No external requests are made at generation time or at view time.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

# ── date helpers ──────────────────────────────────────────────────────────────


def _parse_date(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _monday_of(dt: datetime) -> datetime:
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )


def _make_buckets(earliest: datetime, latest: datetime, gran: str) -> list[str]:
    keys: list[str] = []
    if gran == "day":
        cur = earliest.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        end = latest.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        while cur <= end:
            keys.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
    else:
        cur = _monday_of(earliest.replace(tzinfo=None))
        end = _monday_of(latest.replace(tzinfo=None))
        while cur <= end:
            keys.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(weeks=1)
    return keys


def _bucket_key(dt: datetime, gran: str) -> str:
    naive = dt.replace(tzinfo=None)
    if gran == "day":
        return naive.strftime("%Y-%m-%d")
    return _monday_of(naive).strftime("%Y-%m-%d")


# ── aggregation ───────────────────────────────────────────────────────────────


def aggregate_report_data(
    goals: list[dict[str, Any]],
    days: int | None,
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

    if not closed:
        return _empty_data()

    parsed: list[tuple[dict[str, Any], datetime]] = [
        (g, dt) for g in closed if (dt := _parse_date(g["finished_at"])) is not None
    ]
    if not parsed:
        return _empty_data()

    dates = [dt for _, dt in parsed]
    earliest, latest = min(dates), max(dates)
    span_days = (latest - earliest).days
    gran = "day" if span_days <= 30 else "week"

    buckets = _make_buckets(earliest, latest, gran)
    bucket_set = set(buckets)

    c1: dict[str, int] = {b: 0 for b in buckets}
    c2_retry: dict[str, int] = {b: 0 for b in buckets}
    c2_attempts: dict[str, list[int]] = {b: [] for b in buckets}
    c3_inp: dict[str, int] = {b: 0 for b in buckets}
    c3_cac: dict[str, int] = {b: 0 for b in buckets}
    c3_out: dict[str, int] = {b: 0 for b in buckets}
    c4: dict[str, list[float]] = {}

    for g, dt in parsed:
        bk = _bucket_key(dt, gran)
        if bk not in bucket_set:
            continue

        status = g.get("status")
        attempts = max(1, int(g.get("attempts") or 1))

        if status == "success":
            c1[bk] += 1

        c2_attempts[bk].append(attempts)
        if attempts > 1:
            c2_retry[bk] += 1

        c3_inp[bk] += int(g.get("input_tokens") or 0)
        c3_cac[bk] += int(g.get("cached_input_tokens") or 0)
        c3_out[bk] += int(g.get("output_tokens") or 0)

        if status == "success" and g.get("cost_usd") is not None:
            c4.setdefault(bk, []).append(float(g["cost_usd"]))

    c4_pairs = [(b, sum(v) / len(v)) for b, v in c4.items() if v]

    def _avg_or_none(lst: list[int]) -> float | None:
        return round(sum(lst) / len(lst), 2) if lst else None

    return {
        "granularity": gran,
        "buckets": buckets,
        "chart1": [c1[b] for b in buckets],
        "chart2_bar": [c2_retry[b] for b in buckets],
        "chart2_line": [_avg_or_none(c2_attempts[b]) for b in buckets],
        "chart3_input": [c3_inp[b] for b in buckets],
        "chart3_cached": [c3_cac[b] for b in buckets],
        "chart3_output": [c3_out[b] for b in buckets],
        "chart4_buckets": [p[0] for p in c4_pairs],
        "chart4_values": [round(p[1], 4) for p in c4_pairs],
    }


def _empty_data() -> dict[str, Any]:
    return {
        "granularity": "day",
        "buckets": [],
        "chart1": [],
        "chart2_bar": [],
        "chart2_line": [],
        "chart3_input": [],
        "chart3_cached": [],
        "chart3_output": [],
        "chart4_buckets": [],
        "chart4_values": [],
    }


# ── HTML rendering ────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codex Metrics Report</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #f8fafc;
    color: #1e293b;
    padding: 32px 24px;
    min-height: 100vh;
  }
  header {
    margin-bottom: 32px;
  }
  header h1 {
    font-size: 24px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 4px;
  }
  header p {
    font-size: 13px;
    color: #64748b;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
    gap: 24px;
  }
  .card {
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04);
    padding: 24px;
  }
  .card h2 {
    font-size: 14px;
    font-weight: 600;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom: 4px;
  }
  .card .subtitle {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 16px;
  }
  canvas { display: block; width: 100%; }
  .legend {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-top: 12px;
    font-size: 12px;
    color: #475569;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .empty-state {
    height: 240px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #94a3b8;
    font-size: 14px;
  }
</style>
</head>
<body>
<header>
  <h1>Codex Metrics</h1>
  <p>Generated {GENERATED_AT} &nbsp;·&nbsp; {GRANULARITY_LABEL}</p>
</header>

<div class="grid">

  <div class="card">
    <h2>Successful Tasks</h2>
    <p class="subtitle">Closed goals with status = success per {GRAN_NOUN}</p>
    <canvas id="c1" height="240"></canvas>
  </div>

  <div class="card">
    <h2>Retry Pressure</h2>
    <p class="subtitle">Goals requiring &gt;1 attempt (bars) · avg attempts per closed goal (line)</p>
    <canvas id="c2" height="240"></canvas>
    <div class="legend">
      <div class="legend-item">
        <div class="legend-dot" style="background:#f97316"></div>
        Goals with retries
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#ef4444;border-radius:50%"></div>
        Avg attempts (line)
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Tokens Spent</h2>
    <p class="subtitle">Input · Cached input · Output per {GRAN_NOUN}</p>
    <canvas id="c3" height="240"></canvas>
    <div class="legend">
      <div class="legend-item">
        <div class="legend-dot" style="background:#3b82f6"></div>
        Input
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#93c5fd"></div>
        Cached
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#1d4ed8"></div>
        Output
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Cost per Successful Task</h2>
    <p class="subtitle">USD · only buckets with &ge;1 success with known cost</p>
    <canvas id="c4" height="240"></canvas>
  </div>

</div>

<script>
const DATA = {DATA_JSON};

// ── utilities ────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n === null || n === undefined) return '';
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (abs >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (abs >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  if (abs < 1 && abs > 0) return n.toFixed(3);
  return n % 1 === 0 ? n.toString() : n.toFixed(2);
}

function niceMax(v) {
  if (v <= 0) return 1;
  const magnitude = Math.pow(10, Math.floor(Math.log10(v)));
  const steps = [1, 2, 2.5, 5, 10];
  for (const s of steps) {
    const candidate = magnitude * s;
    if (candidate >= v) return candidate;
  }
  return magnitude * 10;
}

function setupCanvas(id) {
  const el = document.getElementById(id);
  const dpr = window.devicePixelRatio || 1;
  const rect = el.parentElement.getBoundingClientRect();
  const w = rect.width - 48; // card padding
  const h = parseInt(el.getAttribute('height'));
  el.width = w * dpr;
  el.height = h * dpr;
  el.style.width = w + 'px';
  el.style.height = h + 'px';
  const ctx = el.getContext('2d');
  ctx.scale(dpr, dpr);
  return { ctx, w, h };
}

function drawEmpty(ctx, w, h) {
  ctx.fillStyle = '#94a3b8';
  ctx.font = '13px system-ui';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('No data available', w / 2, h / 2);
}

function drawAxes(ctx, ML, MT, cw, ch) {
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(ML, MT);
  ctx.lineTo(ML, MT + ch);
  ctx.lineTo(ML + cw, MT + ch);
  ctx.stroke();
}

function drawYGrid(ctx, ML, MT, cw, ch, maxVal, steps, color) {
  for (let i = 0; i <= steps; i++) {
    const y = MT + ch - (i / steps) * ch;
    ctx.strokeStyle = color || '#f1f5f9';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(ML, y);
    ctx.lineTo(ML + cw, y);
    ctx.stroke();
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(fmt((i / steps) * maxVal), ML - 6, y);
  }
}

function drawXLabels(ctx, labels, ML, MT, cw, ch, step) {
  const n = labels.length;
  const gap = cw / n;
  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px system-ui';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'top';
  for (let i = 0; i < n; i += step) {
    const x = ML + i * gap + gap / 2;
    ctx.save();
    ctx.translate(x, MT + ch + 6);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(labels[i], 0, 0);
    ctx.restore();
  }
}

// ── chart 1: simple bar ──────────────────────────────────────────────────────

function drawBar(id, labels, values, color) {
  const { ctx, w, h } = setupCanvas(id);
  if (!labels.length || Math.max(...values) === 0) { drawEmpty(ctx, w, h); return; }

  const ML = 48, MR = 16, MT = 12, MB = 68;
  const cw = w - ML - MR, ch = h - MT - MB;
  const maxVal = niceMax(Math.max(...values));
  const n = labels.length;
  const gap = cw / n;
  const barW = Math.max(3, gap * 0.65);
  const step = Math.max(1, Math.ceil(n / 12));

  drawYGrid(ctx, ML, MT, cw, ch, maxVal, 4);
  drawAxes(ctx, ML, MT, cw, ch);

  for (let i = 0; i < n; i++) {
    const v = values[i] || 0;
    if (v === 0) continue;
    const x = ML + i * gap + (gap - barW) / 2;
    const barH = (v / maxVal) * ch;
    const y = MT + ch - barH;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x, y, barW, barH, [3, 3, 0, 0]);
    ctx.fill();
    if (barH > 18) {
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 10px system-ui';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(v, x + barW / 2, y + 5);
    }
  }

  drawXLabels(ctx, labels, ML, MT, cw, ch, step);
}

// ── chart 2: combo bar + line ────────────────────────────────────────────────

function drawCombo(id, labels, barValues, lineValues, barColor, lineColor) {
  const { ctx, w, h } = setupCanvas(id);
  const allVals = [...barValues, ...lineValues.filter(v => v !== null)];
  if (!labels.length || allVals.every(v => !v)) { drawEmpty(ctx, w, h); return; }
  const noRetries = barValues.every(v => !v);

  const ML = 48, MR = 48, MT = 12, MB = 68;
  const cw = w - ML - MR, ch = h - MT - MB;
  const n = labels.length;
  const gap = cw / n;
  const barW = Math.max(3, gap * 0.55);
  const step = Math.max(1, Math.ceil(n / 12));

  const maxBar = niceMax(Math.max(...barValues, 1));
  const lineFiltered = lineValues.filter(v => v !== null);
  const maxLine = niceMax(lineFiltered.length ? Math.max(...lineFiltered) : 1);

  // Left Y grid + labels (bar)
  drawYGrid(ctx, ML, MT, cw, ch, maxBar, 4);
  drawAxes(ctx, ML, MT, cw, ch);

  // Right Y labels (line)
  for (let i = 0; i <= 4; i++) {
    const y = MT + ch - (i / 4) * ch;
    ctx.fillStyle = lineColor;
    ctx.font = '10px system-ui';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(fmt((i / 4) * maxLine), ML + cw + 6, y);
  }

  // Bars
  for (let i = 0; i < n; i++) {
    const v = barValues[i] || 0;
    if (v === 0) continue;
    const x = ML + i * gap + (gap - barW) / 2;
    const barH = (v / maxBar) * ch;
    const y = MT + ch - barH;
    ctx.fillStyle = barColor;
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.roundRect(x, y, barW, barH, [3, 3, 0, 0]);
    ctx.fill();
    ctx.globalAlpha = 1;
    if (barH > 18) {
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 10px system-ui';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(v, x + barW / 2, y + 5);
    }
  }

  // Line
  ctx.strokeStyle = lineColor;
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < n; i++) {
    const v = lineValues[i];
    if (v === null) { started = false; continue; }
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (v / maxLine) * ch;
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Dots on line
  for (let i = 0; i < n; i++) {
    const v = lineValues[i];
    if (v === null) continue;
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (v / maxLine) * ch;
    ctx.fillStyle = lineColor;
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  drawXLabels(ctx, labels, ML, MT, cw, ch, step);

  if (noRetries) {
    const msg = 'No retries — all goals completed on first attempt';
    ctx.font = '11px system-ui';
    const msgW = ctx.measureText(msg).width;
    const px = ML + cw / 2 - msgW / 2 - 8;
    const py = MT + 10;
    ctx.fillStyle = '#f0fdf4';
    ctx.beginPath();
    ctx.roundRect(px, py, msgW + 16, 22, 4);
    ctx.fill();
    ctx.fillStyle = '#16a34a';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(msg, px + 8, py + 11);
  }
}

// ── chart 3: stacked bar ─────────────────────────────────────────────────────

function drawStackedBar(id, labels, series, colors) {
  const { ctx, w, h } = setupCanvas(id);
  const totals = labels.map((_, i) => series.reduce((s, ser) => s + (ser[i] || 0), 0));
  if (!labels.length || Math.max(...totals) === 0) { drawEmpty(ctx, w, h); return; }

  const ML = 52, MR = 16, MT = 12, MB = 68;
  const cw = w - ML - MR, ch = h - MT - MB;
  const maxVal = niceMax(Math.max(...totals));
  const n = labels.length;
  const gap = cw / n;
  const barW = Math.max(3, gap * 0.65);
  const step = Math.max(1, Math.ceil(n / 12));

  drawYGrid(ctx, ML, MT, cw, ch, maxVal, 4);
  drawAxes(ctx, ML, MT, cw, ch);

  for (let i = 0; i < n; i++) {
    let base = 0;
    for (let s = 0; s < series.length; s++) {
      const v = series[s][i] || 0;
      if (v === 0) { base += v; continue; }
      const x = ML + i * gap + (gap - barW) / 2;
      const segH = (v / maxVal) * ch;
      const y = MT + ch - (base + v) / maxVal * ch;
      const isTop = s === series.length - 1;
      const isBottom = s === 0;
      ctx.fillStyle = colors[s];
      ctx.beginPath();
      ctx.roundRect(x, y, barW, segH, [
        isTop ? 3 : 0, isTop ? 3 : 0,
        isBottom ? 0 : 0, isBottom ? 0 : 0,
      ]);
      ctx.fill();
      base += v;
    }
  }

  drawXLabels(ctx, labels, ML, MT, cw, ch, step);
}

// ── chart 4: line ────────────────────────────────────────────────────────────

function drawLine(id, labels, values, color) {
  const { ctx, w, h } = setupCanvas(id);
  if (!labels.length || values.every(v => v === null)) { drawEmpty(ctx, w, h); return; }

  const ML = 56, MR = 16, MT = 12, MB = 68;
  const cw = w - ML - MR, ch = h - MT - MB;
  const validValues = values.filter(v => v !== null);
  const maxVal = niceMax(Math.max(...validValues));
  const n = labels.length;
  const gap = cw / n;
  const step = Math.max(1, Math.ceil(n / 12));

  drawYGrid(ctx, ML, MT, cw, ch, maxVal, 4);
  drawAxes(ctx, ML, MT, cw, ch);

  // Area fill
  ctx.fillStyle = color + '18';
  ctx.beginPath();
  let started = false;
  let firstX = 0, lastX = 0, lastY = 0;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null) continue;
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (v / maxVal) * ch;
    if (!started) { ctx.moveTo(x, MT + ch); ctx.lineTo(x, y); firstX = x; started = true; }
    else ctx.lineTo(x, y);
    lastX = x; lastY = y;
  }
  if (started) {
    ctx.lineTo(lastX, MT + ch);
    ctx.closePath();
    ctx.fill();
  }

  // Line
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  started = false;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null) { started = false; continue; }
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (v / maxVal) * ch;
    if (!started) { ctx.moveTo(x, y); started = true; }
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Dots + value labels
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null) continue;
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (v / maxVal) * ch;
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.font = 'bold 10px system-ui';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillText('$' + fmt(v), x, y - 7);
  }

  drawXLabels(ctx, labels, ML, MT, cw, ch, step);
}

// ── render ───────────────────────────────────────────────────────────────────

function render() {
  const d = DATA;
  drawBar('c1', d.buckets, d.chart1, '#22c55e');
  drawCombo('c2', d.buckets, d.chart2_bar, d.chart2_line, '#f97316', '#ef4444');
  drawStackedBar('c3', d.buckets, [d.chart3_input, d.chart3_cached, d.chart3_output], ['#3b82f6', '#93c5fd', '#1d4ed8']);
  drawLine('c4', d.chart4_buckets, d.chart4_values, '#8b5cf6');
}

window.addEventListener('load', render);
window.addEventListener('resize', render);
</script>
</body>
</html>
"""


def render_html_report(data: dict[str, Any], generated_at: str) -> str:
    """Return the full HTML string for the report."""
    gran = data.get("granularity", "day")
    gran_noun = "day" if gran == "day" else "week"
    granularity_label = "Daily buckets" if gran == "day" else "Weekly buckets"

    # Escape </script> sequences so the JSON cannot break out of the script block.
    # This is the standard mitigation for inline JSON-in-HTML.
    safe_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    return (
        _HTML_TEMPLATE
        .replace("{DATA_JSON}", safe_json)
        .replace("{GENERATED_AT}", generated_at)
        .replace("{GRANULARITY_LABEL}", granularity_label)
        .replace("{GRAN_NOUN}", gran_noun)
    )
