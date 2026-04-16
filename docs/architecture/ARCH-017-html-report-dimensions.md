# ARCH-017: Add provider and model dimensions to HTML report

**Priority:** high
**Complexity:** medium
**Status:** open

## Problem

The HTML report (`render-html`) aggregates all data into a single stream with no visibility into provider or model. For a product that tracks AI agent spending across providers and models, this hides the most actionable cost and performance signals.

### UX-1 (high): No breakdown by provider (Claude / Codex)

All four charts aggregate data regardless of which AI provider generated it. A user working with both Claude and Codex cannot see which provider is more expensive, has more retries, or is more efficient.

Data already available but unused in the report:
- Warehouse: `raw_sessions.source` ("claude" / "codex"), `derived_goals.model_provider`
- Ledger: `agent_name` on goal records

### UX-2 (high): No breakdown by model

No chart shows which model was used. Models have dramatically different costs (e.g. opus vs sonnet), but Chart 3 (Token Cost) sums everything together and Chart 4 (Cost per Success) averages across models.

Data already available:
- Ledger: `model` field on goals
- Warehouse: `normalized_usage_events` has model on every row; `derived_goals.model` (NULL today, addressed by ARCH-016)
- Aggregation code already passes `model` to `_apply_token_pricing()` for USD conversion — but then folds the result into a single bucket

### UX-3 (medium): Chart 3 shows $0 when token breakdown is missing

Chart 3 (Token Cost Breakdown) uses `input_tokens + cached_input_tokens + output_tokens`. When these fields are null but `cost_usd` is populated, Chart 3 shows $0 while Chart 4 (Cost per Success) shows real money. The two charts in the same report appear to contradict each other.

Real example from this repo: Chart 3 shows $0 for 10 of 11 days, while Chart 4 shows $147, $140, $4 etc. for those same days.

### UX-4 (medium): Summary strip missing total cost

The summary strip shows Goals Closed, Successes, Avg Cost/Success, and Cost Trend. Total cost — the first question a cost-tracking user asks — is absent.

### UX-5 (low): Cost Trend "n/a" without explanation

When fewer than 4 data points exist, trend is null and shows "n/a" with no hint that more data is needed.

### UX-6 (low): Single-bucket charts with no guidance

When all goals fall in one day/week, charts show a single bar with no trend. No message explains that more history is needed for meaningful charts.

## Proposed solution

### Phase 1: Low-hanging fruit (no schema changes)

1. **Summary strip: add Total Cost card** — sum of `cost_usd` across all successful goals. Straightforward addition to `_GoalSeries` and template.

2. **Chart 3 fallback**: when token breakdown is unavailable but `cost_usd` exists, show a single "Known Cost" series from the ledger instead of three empty token series. Add a subtitle note explaining the source difference.

3. **Cost Trend explanation**: when trend is null, show "need 4+ data points" instead of bare "n/a".

4. **Single-bucket guidance**: when `buckets.length === 1`, show an info banner "Single data point — collect more history for trend analysis".

### Phase 2: Model dimension (depends on ARCH-016)

5. **Chart 3 by model**: instead of stacking input/cached/output, stack by model (or add a toggle between the two views). Each model gets its own color. This directly answers "where is my money going?".

6. **Summary strip: model breakdown line** — e.g. "claude-sonnet-4-6: 80%, claude-opus-4-6: 20%" under the Total Cost card.

7. **Chart 4 by model**: overlay cost-per-success lines per model on the same chart, or add a legend filter.

### Phase 3: Provider dimension

8. **Section-level provider split**: duplicate the Session History section per provider (one for Claude, one for Codex), each with its own Chart 2 (Retries) and Chart 3 (Tokens/Cost). This keeps charts simple while enabling provider comparison.

9. **Provider badge on summary cards**: when multiple providers exist, show which provider contributed to each stat.

## Dependencies

- Phase 2 depends on **ARCH-016** (model propagated to derived tables) for warehouse-sourced charts.
- Phase 1 has no dependencies and can ship independently.

## Validation

- Generate report with mixed-model goals and verify per-model breakdown is visible
- Generate report with both Claude and Codex warehouse data and verify provider split
- Verify Chart 3 fallback renders cost when token breakdown is null but cost_usd exists
- Verify total cost card matches `show --json` summary total_cost_usd
- All existing `test_html_report.py` tests pass unchanged (additive changes)
