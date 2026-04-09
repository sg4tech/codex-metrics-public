---
id: H-034
title: A model_pricing.json may be required before cost-per-task estimates become reliable
status: planned
created: 2026-04-09
---

## Hypothesis

Token counts alone are insufficient for cost analysis. To compute actual USD cost per goal or attempt, the system needs a mapping from model identifier to per-token price (input, output, cached-input). A `model_pricing.json` file — bundled with the package, with optional workspace override — may be the simplest way to provide that mapping for Claude models.

## Expected upside

- Cost per task, cost per goal, and P&L estimates become concrete dollar figures instead of unitless token counts.
- Unlocks meaningful cost/outcome ratios (e.g., cost per confirmed outcome).
- Makes H-003 (cost as guardrail) and H-009 (input/output/cache split) actionable without external tooling.

## Main risks

- Anthropic pricing changes; bundled file drifts unless updated on each price change. Mitigated: user can place a workspace-level override.
- Multiple price tiers exist (Batches API); a flat mapping may oversimplify. Mitigated: batch discount is a scalar modifier (`×0.5`), can be added later without breaking schema.
- Model IDs in events may include date suffixes (`-20251022`). Mitigated: normalize by stripping trailing `-YYYYMMDD` before lookup.

## Decisions (resolved 2026-04-09)

| # | Decision |
|---|---|
| Storage | Bundled in the package as default; workspace-root `model_pricing.json` overrides if present |
| Granularity | Three fields per model: `input_per_1m`, `output_per_1m`, `cached_input_per_1m` (USD per 1M tokens). Batch discount added later as a modifier if needed |
| Model ID normalization | Strip trailing date suffix (`-\d{8}$`) in code before lookup; no aliases field in the file |

## Schema (proposed)

```json
{
  "claude-sonnet-4-6": {
    "input_per_1m": 3.00,
    "output_per_1m": 15.00,
    "cached_input_per_1m": 0.30
  },
  "claude-opus-4-6": {
    "input_per_1m": 15.00,
    "output_per_1m": 75.00,
    "cached_input_per_1m": 1.50
  },
  "claude-haiku-4-5": {
    "input_per_1m": 0.80,
    "output_per_1m": 4.00,
    "cached_input_per_1m": 0.08
  }
}
```

## Confidence

Medium — storage pattern and schema are settled; main remaining risk is keeping the bundled file current.
