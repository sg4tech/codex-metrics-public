"""Self-contained HTML template for the Codex Metrics report.

The template is a single string with four substitution placeholders:
- ``{DATA_JSON}``        — serialised report data dict (JSON)
- ``{GENERATED_AT}``    — human-readable generation timestamp
- ``{GRANULARITY_LABEL}`` — e.g. "Daily buckets"
- ``{GRAN_NOUN}``        — e.g. "day" or "week"

All chart rendering happens in the browser via embedded vanilla JS / Canvas 2D.
No external requests are made at generation time or at view time.
"""

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
  header { margin-bottom: 20px; }
  header h1 {
    font-size: 24px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 4px;
  }
  header p { font-size: 13px; color: #64748b; }

  /* summary strip */
  .summary-strip {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 28px;
  }
  .stat-card {
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,.07);
    padding: 14px 20px;
    min-width: 140px;
    flex: 1;
  }
  .stat-value {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
    margin-bottom: 2px;
    white-space: nowrap;
  }
  .stat-label {
    font-size: 11px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: .05em;
  }

  /* charts grid */
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
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
  .legend-item[data-toggleable] { cursor: pointer; user-select: none; transition: opacity .15s; }
  .legend-item[data-toggleable]:hover { opacity: .75; }
  .legend-item[data-toggleable].off { opacity: .35; text-decoration: line-through; }

  /* section dividers */
  .section-header {
    margin: 32px 0 16px;
    padding-bottom: 10px;
    border-bottom: 1.5px solid #e2e8f0;
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .section-header h3 {
    font-size: 11px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: .08em;
    margin: 0;
  }
  .section-header p {
    font-size: 12px;
    color: #94a3b8;
    margin: 0;
  }
  .src-badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .05em;
    padding: 2px 7px;
    border-radius: 4px;
  }
  .src-badge.ledger { background: #f1f5f9; color: #64748b; }
  .src-badge.history { background: #f0fdf4; color: #15803d; }
</style>
</head>
<body>
<header>
  <h1>Codex Metrics</h1>
  <p>Generated {GENERATED_AT} &nbsp;·&nbsp; {GRANULARITY_LABEL}</p>
</header>

<div class="summary-strip" id="summary-strip"></div>

<div id="sh-ledger" class="section-header"></div>
<div class="grid">

  <div class="card">
    <h2>Successful Tasks</h2>
    <p class="subtitle">Closed goals with status = success per {GRAN_NOUN} · by type</p>
    <canvas id="c1" height="240"></canvas>
    <div class="legend" id="c1-legend"></div>
  </div>

  <div class="card">
    <h2>Cost per Successful Task</h2>
    <p class="subtitle">USD · avg cost per success per {GRAN_NOUN} · outliers clipped</p>
    <canvas id="c4" height="240"></canvas>
  </div>

</div>

<div id="sh-history" class="section-header"></div>
<div class="grid">

  <div class="card">
    <h2>Retry Pressure</h2>
    <p class="subtitle" id="c2-subtitle"></p>
    <canvas id="c2" height="240"></canvas>
    <div class="legend" id="c2-legend"></div>
  </div>

  <div class="card">
    <h2 id="c3-title">Tokens Spent</h2>
    <p class="subtitle" id="c3-subtitle"></p>
    <canvas id="c3" height="240"></canvas>
    <div class="legend" id="c3-legend"></div>
  </div>

</div>

<div id="sh-practice" class="section-header"></div>
<div class="grid" id="grid-practice">

  <div class="card" id="c5-card" style="grid-column: 1 / -1;">
    <h2>Practice Events by Name</h2>
    <p class="subtitle" id="c5-subtitle"></p>
    <canvas id="c5" height="280"></canvas>
    <div class="legend" id="c5-legend"></div>
  </div>

</div>

<script>
const DATA = {DATA_JSON};

// ── series toggle state ───────────────────────────────────────────────────────

// Chart 3's series count depends on how many distinct models appear in the
// data, so c3 toggles are initialized dynamically in render().
const seriesToggles = { c1: [true, true, true], c3: [] };

function toggleSeries(chartId, idx) {
  const t = seriesToggles[chartId];
  // Keep at least one series visible.
  if (t.filter(Boolean).length === 1 && t[idx]) return;
  t[idx] = !t[idx];
  redrawStackedChart(chartId);
}

function redrawStackedChart(chartId) {
  const d = DATA;
  if (chartId === 'c1') {
    renderC1Legend();
    drawStackedBar('c1', d.buckets, [d.chart1_product, d.chart1_meta, d.chart1_retro],
      ['#22c55e', '#94a3b8', '#f59e0b'], false, '', seriesToggles.c1);
  } else if (chartId === 'c3') {
    renderC3Legend();
    const pfx = d.chart3_mode === 'cost' ? '$' : '';
    const sArr = (d.chart3_series || []).map(s => s.values);
    const cArr = (d.chart3_series || []).map(s => s.color);
    drawStackedBar('c3', d.buckets, sArr, cArr, true, pfx, seriesToggles.c3);
  }
}

function makeLegendItem(color, label, chartId, idx) {
  const on = seriesToggles[chartId][idx];
  return '<div class="legend-item' + (on ? '' : ' off') + '" data-toggleable="1" ' +
    'data-chart="' + chartId + '" data-idx="' + idx + '" ' +
    'onclick="toggleSeries(this.dataset.chart, +this.dataset.idx)">' +
    '<div class="legend-dot" style="background:' + color + '"></div>' + label + '</div>';
}

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
    if (magnitude * s >= v) return magnitude * s;
  }
  return magnitude * 10;
}

// Returns { max, clipped, threshold } — clips Y axis when outliers skew scale.
// Uses median as the baseline: if max > 4× median, the top values are outliers.
function smartMax(values) {
  const valid = values.filter(v => v != null).sort((a, b) => a - b);
  if (!valid.length) return { max: 1, clipped: false };
  const rawMax = valid[valid.length - 1];
  if (valid.length <= 2) return { max: niceMax(rawMax), clipped: false };
  const mid = Math.floor(valid.length / 2);
  const median = valid.length % 2 ? valid[mid] : (valid[mid - 1] + valid[mid]) / 2;
  if (median > 0 && rawMax > 4 * median) {
    const cap = niceMax(median * 2.5);
    return { max: cap, clipped: true, threshold: cap };
  }
  return { max: niceMax(rawMax), clipped: false };
}

function setupCanvas(id) {
  const el = document.getElementById(id);
  const dpr = window.devicePixelRatio || 1;
  const rect = el.parentElement.getBoundingClientRect();
  const w = rect.width - 48;
  // Cache the intended height: setting el.height reflects back to the attribute,
  // so reading getAttribute on a re-draw would see the inflated dpr-multiplied value.
  if (!el.dataset.intendedHeight) el.dataset.intendedHeight = el.getAttribute('height');
  const h = parseInt(el.dataset.intendedHeight);
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

function drawYGrid(ctx, ML, MT, cw, ch, maxVal, steps, yPrefix) {
  for (let i = 0; i <= steps; i++) {
    const y = MT + ch - (i / steps) * ch;
    ctx.strokeStyle = '#f1f5f9';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(ML, y);
    ctx.lineTo(ML + cw, y);
    ctx.stroke();
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText((yPrefix || '') + fmt((i / steps) * maxVal), ML - 6, y);
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

// ── chart 1: stacked bar by goal type ────────────────────────────────────────

function drawStackedBar(id, labels, series, colors, useSmartMax, labelPrefix, toggles) {
  const { ctx, w, h } = setupCanvas(id);
  const activeSeries = series.map((s, i) => (!toggles || toggles[i]) ? s : s.map(() => 0));
  const totals = labels.map((_, i) => activeSeries.reduce((s, ser) => s + (ser[i] || 0), 0));
  if (!labels.length || Math.max(...totals) === 0) { drawEmpty(ctx, w, h); return; }

  const ML = 52, MR = 16, MT = 20, MB = 68;
  const cw = w - ML - MR, ch = h - MT - MB;
  const { max: maxVal, clipped } = useSmartMax ? smartMax(totals) : { max: niceMax(Math.max(...totals)), clipped: false };
  const n = labels.length;
  const gap = cw / n;
  const barW = Math.max(3, gap * 0.65);
  const step = Math.max(1, Math.ceil(n / 12));

  drawYGrid(ctx, ML, MT, cw, ch, maxVal, 4, labelPrefix);
  drawAxes(ctx, ML, MT, cw, ch);

  if (clipped) {
    ctx.strokeStyle = '#fca5a5';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(ML, MT);
    ctx.lineTo(ML + cw, MT);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#fca5a5';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('clipped', ML + 4, MT - 2);
  }

  for (let i = 0; i < n; i++) {
    let base = 0;
    const total = totals[i];
    const isOutlier = clipped && total > maxVal;
    for (let s = 0; s < activeSeries.length; s++) {
      const v = activeSeries[s][i] || 0;
      if (v === 0) { base += v; continue; }
      const x = ML + i * gap + (gap - barW) / 2;
      const clampedBase = Math.min(base, maxVal);
      const clampedTop = Math.min(base + v, maxVal);
      const segH = (clampedTop - clampedBase) / maxVal * ch;
      if (segH <= 0) { base += v; continue; }
      const y = MT + ch - clampedTop / maxVal * ch;
      const isTop = (s === activeSeries.length - 1) || activeSeries.slice(s + 1).every(ser => !ser[i]);
      ctx.fillStyle = isOutlier ? colors[s] + 'aa' : colors[s];
      ctx.beginPath();
      ctx.roundRect(x, y, barW, segH, [isTop && !isOutlier ? 3 : 0, isTop && !isOutlier ? 3 : 0, 0, 0]);
      ctx.fill();
      base += v;
    }
    // Total label — always use fmt() for readability
    if (total > 0) {
      const labelY = isOutlier ? MT + 2 : MT + ch - Math.min(total, maxVal) / maxVal * ch;
      if (!isOutlier && labelY < MT + 4) continue;
      ctx.fillStyle = isOutlier ? '#dc2626' : '#475569';
      ctx.font = 'bold 10px system-ui';
      ctx.textAlign = 'center';
      ctx.textBaseline = isOutlier ? 'top' : 'bottom';
      ctx.fillText((labelPrefix || '') + fmt(total), ML + i * gap + gap / 2, labelY + (isOutlier ? 2 : -2));
    }
  }

  drawXLabels(ctx, labels, ML, MT, cw, ch, step);
}

// ── chart 2: combo bar + line ────────────────────────────────────────────────

function drawCombo(id, labels, barValues, lineValues, barColor, lineColor, linePct) {
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

  drawYGrid(ctx, ML, MT, cw, ch, maxBar, 4);
  drawAxes(ctx, ML, MT, cw, ch);

  // Right Y labels (line axis)
  for (let i = 0; i <= 4; i++) {
    const y = MT + ch - (i / 4) * ch;
    ctx.fillStyle = lineColor;
    ctx.font = '10px system-ui';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const val = (i / 4) * maxLine;
    ctx.fillText(linePct ? fmt(val) + '%' : fmt(val), ML + cw + 6, y);
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
    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Dots
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


// ── chart 4: line with outlier clipping ──────────────────────────────────────

function drawLine(id, labels, values, color) {
  const { ctx, w, h } = setupCanvas(id);
  if (!labels.length || values.every(v => v === null)) { drawEmpty(ctx, w, h); return; }

  const ML = 56, MR = 16, MT = 20, MB = 68;
  const cw = w - ML - MR, ch = h - MT - MB;
  const n = labels.length;
  const gap = cw / n;
  const step = Math.max(1, Math.ceil(n / 12));

  const { max: maxVal, clipped, threshold } = smartMax(values);

  drawYGrid(ctx, ML, MT, cw, ch, maxVal, 4);
  drawAxes(ctx, ML, MT, cw, ch);

  // Clip line
  if (clipped) {
    ctx.strokeStyle = '#fca5a5';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(ML, MT);
    ctx.lineTo(ML + cw, MT);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#fca5a5';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('clipped', ML + 4, MT - 2);
  }

  // Area fill (only for non-clipped values)
  ctx.fillStyle = color + '18';
  ctx.beginPath();
  let areaStarted = false;
  let lastX = 0;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null) continue;
    const clamped = Math.min(v, maxVal);
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (clamped / maxVal) * ch;
    if (!areaStarted) { ctx.moveTo(x, MT + ch); ctx.lineTo(x, y); areaStarted = true; }
    else ctx.lineTo(x, y);
    lastX = x;
  }
  if (areaStarted) { ctx.lineTo(lastX, MT + ch); ctx.closePath(); ctx.fill(); }

  // Line
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null) { started = false; continue; }
    const clamped = Math.min(v, maxVal);
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (clamped / maxVal) * ch;
    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Dots + labels
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null) continue;
    const isOutlier = clipped && v > threshold;
    const clamped = Math.min(v, maxVal);
    const x = ML + i * gap + gap / 2;
    const y = MT + ch - (clamped / maxVal) * ch;

    if (isOutlier) {
      // Draw outlier as a diamond marker at clip boundary
      ctx.fillStyle = '#fca5a5';
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, MT + 2); ctx.lineTo(x + 5, MT + 8);
      ctx.lineTo(x, MT + 14); ctx.lineTo(x - 5, MT + 8);
      ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#dc2626';
      ctx.font = 'bold 10px system-ui';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText('$' + fmt(v), x, MT);
    } else {
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
  }

  drawXLabels(ctx, labels, ML, MT, cw, ch, step);
}

// ── summary strip ─────────────────────────────────────────────────────────────

function renderSummary() {
  const s = DATA.summary;
  const strip = document.getElementById('summary-strip');
  if (!s || !strip) return;

  const trendMap = { improving: ['↓ improving', '#16a34a'], worsening: ['↑ worsening', '#dc2626'], stable: ['→ stable', '#64748b'] };
  const [trendText, trendColor] = trendMap[s.cost_trend] || ['n/a', '#94a3b8'];

  const stats = [
    { value: s.total_closed,                                       label: 'Goals closed' },
    { value: s.success_count + ' (' + s.success_rate_pct + '%)',   label: 'Successes' },
    { value: s.total_cost_usd != null ? '$' + s.total_cost_usd : 'n/a', label: 'Total cost' },
    { value: s.avg_cost_usd != null ? '$' + s.avg_cost_usd : 'n/a', label: 'Avg cost / success' },
    { value: trendText, label: 'Cost trend', color: trendColor },
  ];

  strip.innerHTML = stats.map(st =>
    '<div class="stat-card">' +
      '<div class="stat-value"' + (st.color ? ' style="color:' + st.color + '"' : '') + '>' + st.value + '</div>' +
      '<div class="stat-label">' + st.label + '</div>' +
    '</div>'
  ).join('');
}

// ── section headers ──────────────────────────────────────────────────────────

function renderSectionHeaders() {
  const d = DATA;

  function dateRange(from, to) {
    if (!from) return 'no data';
    return from === to ? from : from + ' \u2192 ' + to;
  }

  const ledgerEl = document.getElementById('sh-ledger');
  if (ledgerEl) {
    const range = dateRange(d.ledger_date_from, d.ledger_date_to);
    const count = d.summary ? ' \u00b7 ' + d.summary.total_closed + ' goals' : '';
    ledgerEl.innerHTML =
      '<h3>Goals Ledger</h3>' +
      '<span class="src-badge ledger">ndjson</span>' +
      '<p>' + range + count + '</p>';
  }

  const historyEl = document.getElementById('sh-history');
  if (historyEl) {
    const range = dateRange(d.history_date_from, d.history_date_to);
    historyEl.innerHTML =
      '<h3>Session History</h3>' +
      '<span class="src-badge history">warehouse</span>' +
      '<p>' + range + '</p>';
  }

  const practiceEl = document.getElementById('sh-practice');
  const practiceCard = document.getElementById('c5-card');
  const practiceGrid = document.getElementById('grid-practice');
  const c5 = d.chart5 || {};
  if (practiceEl) {
    if (c5.source === 'warehouse' && (c5.labels || []).length) {
      const shown = c5.shown_events || 0;
      const total = c5.total_events || 0;
      const omitted = Math.max(0, total - shown);
      const omittedNote = omitted > 0
        ? ' \u00b7 ' + omitted + ' events in ' + ((c5.labels || []).length >= 15 ? 'long tail' : 'other names') + ' not shown'
        : '';
      practiceEl.innerHTML =
        '<h3>Practice Events</h3>' +
        '<span class="src-badge history">warehouse</span>' +
        '<p>' + total + ' events across ' + (c5.labels || []).length + ' names' + omittedNote + '</p>';
      if (practiceCard) practiceCard.style.display = '';
      if (practiceGrid) practiceGrid.style.display = '';
    } else {
      // Hide the whole section when there are no practice events to show.
      practiceEl.innerHTML = '';
      if (practiceCard) practiceCard.style.display = 'none';
      if (practiceGrid) practiceGrid.style.display = 'none';
    }
  }
}

// ── render all ───────────────────────────────────────────────────────────────

function renderC1Legend() {
  const leg = document.getElementById('c1-legend');
  if (!leg) return;
  leg.innerHTML = [
    makeLegendItem('#22c55e', 'Product', 'c1', 0),
    makeLegendItem('#94a3b8', 'Meta', 'c1', 1),
    makeLegendItem('#f59e0b', 'Retro', 'c1', 2),
  ].join('');
}

function renderC3Legend() {
  const series = DATA.chart3_series || [];
  const leg = document.getElementById('c3-legend');
  if (leg) leg.innerHTML = series.map((s, i) => makeLegendItem(s.color, s.name, 'c3', i)).join('');
}

function renderChart3Meta() {
  const cost = DATA.chart3_mode === 'cost';
  const gran = DATA.granularity === 'day' ? 'day' : 'week';
  const title = document.getElementById('c3-title');
  const sub = document.getElementById('c3-subtitle');
  const src = DATA.chart3_source === 'warehouse' ? ' \u00b7 source: history' : '';
  if (title) title.textContent = cost ? 'Cost by Model' : 'Tokens by Model';
  if (sub) sub.textContent = (cost ? 'USD per ' + gran : 'Tokens per ' + gran) +
    ' \u00b7 stacked by model' + src;
  renderC3Legend();
}

// Chart 5 palette — agent/skill/other. Green for Agent (subagent spawn),
// blue for Skill (scripted workflow), slate for the "other" bucket.
const C5_COLORS = ['#22c55e', '#3b82f6', '#94a3b8'];
const C5_LABELS = ['Agent', 'Skill', 'Other'];

function renderChart5() {
  const c5 = DATA.chart5 || {};
  const labels = c5.labels || [];
  if (!labels.length) return;

  const sub = document.getElementById('c5-subtitle');
  if (sub) {
    sub.textContent = 'Top ' + labels.length + ' practice names by count \u00b7 stacked by kind \u00b7 source: history';
  }

  const leg = document.getElementById('c5-legend');
  if (leg) {
    // Only show legend items for kinds that actually have data so the legend
    // doesn't mislead on a Skill-only or Agent-only dataset.
    const totals = [
      (c5.agent || []).reduce((a, b) => a + b, 0),
      (c5.skill || []).reduce((a, b) => a + b, 0),
      (c5.other || []).reduce((a, b) => a + b, 0),
    ];
    const items = [];
    for (let i = 0; i < C5_LABELS.length; i++) {
      if (totals[i] > 0) {
        items.push('<div class="legend-item"><div class="legend-dot" style="background:' +
          C5_COLORS[i] + '"></div>' + C5_LABELS[i] + ' (' + totals[i] + ')</div>');
      }
    }
    leg.innerHTML = items.join('');
  }

  const series = [c5.agent || [], c5.skill || [], c5.other || []];
  // Chart 5 is not toggleable — pass a tri-state "all visible" array to keep
  // drawStackedBar's toggle-aware path happy.
  drawStackedBar('c5', labels, series, C5_COLORS, false, '', [true, true, true]);
}

function renderChart2Meta() {
  const warehouse = DATA.chart2_source === 'warehouse';
  const sub = document.getElementById('c2-subtitle');
  const leg = document.getElementById('c2-legend');
  if (sub) sub.textContent = warehouse
    ? 'Threads requiring >1 session (bars) \u00b7 retry rate % (line) \u00b7 source: history'
    : 'Goals requiring >1 attempt (bars) \u00b7 avg attempts per closed goal (line) \u00b7 source: ledger';
  if (leg) leg.innerHTML = warehouse
    ? '<div class="legend-item"><div class="legend-dot" style="background:#f97316"></div>Retry threads</div>' +
      '<div class="legend-item"><div class="legend-dot" style="background:#ef4444;border-radius:50%"></div>Retry rate % (line)</div>'
    : '<div class="legend-item"><div class="legend-dot" style="background:#f97316"></div>Goals with retries</div>' +
      '<div class="legend-item"><div class="legend-dot" style="background:#ef4444;border-radius:50%"></div>Avg attempts (line)</div>';
}

function render() {
  const d = DATA;
  // Initialize c3 toggles once to match the number of model series; preserve
  // user toggles on window-resize re-renders.
  const c3Len = (d.chart3_series || []).length;
  if (seriesToggles.c3.length !== c3Len) {
    seriesToggles.c3 = new Array(c3Len).fill(true);
  }
  renderSummary();
  renderSectionHeaders();
  renderChart2Meta();
  renderChart3Meta();
  renderC1Legend();
  drawStackedBar('c1', d.buckets, [d.chart1_product, d.chart1_meta, d.chart1_retro], ['#22c55e', '#94a3b8', '#f59e0b'], false, '', seriesToggles.c1);
  drawCombo('c2', d.buckets, d.chart2_bar, d.chart2_line, '#f97316', '#ef4444', d.chart2_source === 'warehouse');
  const c3Prefix = d.chart3_mode === 'cost' ? '$' : '';
  const c3Values = (d.chart3_series || []).map(s => s.values);
  const c3Colors = (d.chart3_series || []).map(s => s.color);
  drawStackedBar('c3', d.buckets, c3Values, c3Colors, true, c3Prefix, seriesToggles.c3);
  drawLine('c4', d.chart4_buckets, d.chart4_values, '#8b5cf6');
  renderChart5();
}

window.addEventListener('load', render);
window.addEventListener('resize', render);
</script>
</body>
</html>
"""
