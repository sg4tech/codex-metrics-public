# Automatic Usage Sync Retro

## Situation

The project had already gained pricing formulas and model-based USD calculation, but real task records still mostly showed `cost_usd: null` and `tokens_total: null`.

This created a product gap: the metrics schema supported cost tracking, while the actual workflow still depended on manual usage entry, which was not acceptable for the intended usage model.

## What Happened

- Pricing configuration and token-based USD calculation were added to the updater.
- That solved the arithmetic part of cost tracking, but not the data-ingestion problem.
- A product review exposed the mismatch directly: the report still showed null cost fields for most real tasks.
- Local Codex data sources were then investigated instead of expanding manual CLI flows.
- Two usable local SQLite sources were identified:
  - `~/.codex/state_5.sqlite` for thread metadata
  - `~/.codex/logs_1.sqlite` for `response.completed` telemetry events
- The updater was extended to:
  - infer the Codex thread for the current repository
  - collect usage telemetry inside each task time window
  - compute USD cost from the pricing table
  - write `cost_usd` and `tokens_total` automatically
  - backfill existing tasks through `sync-codex-usage`
- Validation was expanded to 29 automated tests, and the current task was successfully auto-populated from local telemetry.
- Historical tasks remained null when the required telemetry was not present in the local logs for their task windows.

## Root Cause

The original implementation solved the wrong layer first.

The project focused on how to calculate price once token counts were known, but the real bottleneck was how to obtain trustworthy usage data without manual input. As a result, the cost model existed before the ingestion pipeline, and the product still failed the practical requirement of automatic tracking.

## Retrospective

The useful correction was to stop treating pricing as the main problem and reframe the feature as an ingestion problem with a pricing step attached to it.

That shift led to a much better solution. Instead of adding more manual flags or semi-automatic workflows, the implementation moved to the real source of truth already available on the local machine. This preserved the existing CLI while making the feature materially more valuable.

The remaining null historical records are not a failure of the current implementation. They are a visibility limit of the available telemetry. Preserving null in that case is the correct behavior because it keeps the metrics honest.

## Conclusions

- Automatic cost tracking only becomes real when usage ingestion is automatic too.
- Pricing formulas alone are insufficient as a product feature.
- Task windows plus local telemetry provide a workable and reproducible basis for auto-tracking.
- Historical backfill must remain evidence-based; missing telemetry should stay null instead of being inferred.

## Permanent Changes

- Treat cost tracking as a two-part feature: ingestion first, pricing second.
- Prefer local source-of-truth telemetry over manual bookkeeping when Codex data is available.
- Keep historical gaps explicit as `null` when the logs do not support reconstruction.
- Preserve automated tests for both pricing math and telemetry ingestion.
- When a metric field exists but is still mostly null in real task records, treat that as a product gap rather than assuming the feature is complete.
