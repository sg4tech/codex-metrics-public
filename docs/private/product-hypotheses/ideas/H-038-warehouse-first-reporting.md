---
id: H-038
title: Warehouse-first reporting may recover full project history and make the ndjson ledger a thin classification overlay
status: confirmed
created: 2026-04-11
confirmed: 2026-04-11
---

## Hypothesis

The HTML report currently reads Charts 1, 3, and 4 from `events.ndjson` and only Chart 2 from the warehouse. This creates a structural gap: ndjson starts on 2026-04-07, so three of four charts show only ~4 days of history, while the warehouse covers the full project life from 2026-03-29 (236+ sessions). Switching the report to warehouse-first for token and volume data would immediately surface full history without any ledger migration.

## Core idea

Split the data contract by what each source actually knows:

| Source | What it provides |
|---|---|
| Warehouse (`derived_session_usage` JOIN `derived_goals`) | thread count, input/cached/output tokens, model, first/last seen, retry count |
| ndjson ledger | `goal_type` (product/meta/retro), human-readable title, `result_fit`, `failure_reason`, explicit close status |

Chart assignments:

- **Chart 1 (tasks by type)** — stays ndjson-driven; goal_type is not inferable from the warehouse without an LLM classifier. Can be supplemented later (H-036).
- **Chart 2 (retry pressure)** — already warehouse-driven. No change.
- **Chart 3 (token cost)** — switch to warehouse: `SUM(input_tokens)`, `SUM(cached_input_tokens)`, `SUM(output_tokens)` per day from `derived_session_usage JOIN derived_goals WHERE cwd = ?`. Covers full history.
- **Chart 4 (cache hit ratio)** — switch to warehouse: `cached_input_tokens / (input_tokens + cached_input_tokens)` per bucket. Covers full history.

## Expected upside

- Charts 3 and 4 immediately gain ~2 weeks of missing history (2026-03-29 → 2026-04-06) at zero migration cost.
- Warehouse token data is more accurate than ndjson (ndjson `input_tokens` was often NULL or missing for manual start/finish goals).
- Cost calculation becomes authoritative: model field is populated in warehouse, pricing lookup already works.
- ndjson role simplifies: it becomes a thin classification overlay (goal_type, title, result_fit) rather than a primary data source.

## Main risks

| Risk | Notes |
|---|---|
| Warehouse not always present | Fallback to ndjson required when warehouse is absent (same pattern already used for Chart 2) |
| gpt-5.4 tokens not in warehouse | Older Codex sessions show `usage_event_count > 0` but token columns are NULL in `derived_session_usage` — those buckets would show 0 cost until pricing is backfilled |
| Thread vs goal granularity | Warehouse granularity is thread (session), not goal. Multiple threads for the same task inflate daily counts slightly. Acceptable for trend charts. |
| Chart 1 stays ndjson-only | Goal_type chart still only shows post-April-7 history until H-036 (auto-classification) is implemented. |

## Implementation sketch

1. Add `aggregate_warehouse_tokens(warehouse_path, cwd, buckets, gran)` → `(inp[], cache[], out[])` in `html_report.py` — mirrors `_aggregate_warehouse_retry()` pattern.
2. In `handle_render_html` (`commands.py`): query `derived_session_usage JOIN derived_goals` grouped by `DATE(last_seen_at)`, pass result to `aggregate_report_data`.
3. `aggregate_report_data`: if warehouse token data present, use it for chart3 instead of ndjson goal tokens. Mark `chart3_source: "warehouse" | "ledger"` similarly to `chart2_source`.
4. Chart 4 (cache hit ratio): compute `cache / (inp + cache)` from warehouse aggregates if available.

## Open decisions

| # | Question |
|---|---|
| 1 | Should Chart 3 show warehouse cost or warehouse raw tokens when warehouse is present? Cost preferred (pricing already wired). |
| 2 | Should warehouse and ndjson totals be reconciled, or is warehouse always preferred when present? Prefer warehouse — it's the authoritative signal. |
| 3 | Should the summary card (`total_cost_usd`) also switch to warehouse? Yes — ndjson costs are less reliable. |

## Implementation (2026-04-11)

Implemented as described. Key decisions made during implementation:

- Charts 3 and 4 moved to the **Session History** section; Charts 1 and 4 remain in the **Goals Ledger** section. The report now has explicit section headers showing the data source badge, date range, and goal count for each section.
- `_apply_token_pricing()` extracted in `_report_aggregation.py` to deduplicate the pricing logic that existed in both the warehouse path and the ndjson fallback path.
- Sessions with unknown model pricing (e.g. old gpt-5.4 sessions) contribute $0 to the cost chart rather than raw token counts — prevents garbage values on a USD-denominated axis.
- `html_report.py` split into four modules (`_report_buckets`, `_report_aggregation`, `_report_template`, `html_report` facade) as part of the same task.
- Open decision #3 (summary card) resolved: `total_cost_usd` in the summary strip now reflects warehouse data when available.

## Confidence

Confirmed — implemented and shipped. Charts 3 and 4 now cover the full warehouse history from 2026-03-31.

## Relationship to other hypotheses

- Supersedes the ndjson-primary assumption in the current render pipeline.
- Prerequisite for H-036 (full auto-tracking) — establishes warehouse as trusted reporting source.
- Complements H-035 (warehouse retry pressure) — applies the same pattern to token/cost charts.
