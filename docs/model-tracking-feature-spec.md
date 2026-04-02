# Feature Spec: Persist Model Identity For Analysis

## Status

- Draft date: `2026-04-02`
- Owner: `product / metrics`
- Intended audience: `development team`
- Related hypothesis: `H-012` in `docs/product-hypotheses.md`

## Problem

`codex-metrics` already uses a model name when it calculates token-based cost, but the stored metrics history does not treat the model as first-class analysis data.

That creates a few gaps:

- we can see the cost of a goal, but not always the model behind it
- we cannot reliably compare quality and retry pressure across model choices
- a cheaper model can look good in aggregate even if it caused more rework
- if a goal uses more than one model across retries, the history is harder to interpret than it should be

For an agent-first metrics product, model choice is a useful explanatory dimension, not just pricing input.

## Goal

Persist the model used for each attempt as first-class data, and expose a safe goal-level summary when the model is unambiguous.

After this feature, analyzing agents should be able to answer:

1. which model was used for a given goal or attempt
2. whether a cheaper model increased retries or rework
3. whether model choice explains differences in cost, fit, or failure pressure
4. whether the `mini-first` experiment is actually improving economics without hurting quality

## Non-Goals

This feature should not:

- change the default model policy itself
- introduce provider-specific public commands or required parameters
- require perfect historical backfill before shipping
- guess model identity when the source data does not provide it
- add a separate human-only reporting surface

## User Value

Primary user:

- AI agents that analyze metrics and recommend workflow changes

Secondary user:

- human sponsor who receives the synthesized conclusion later

Why this matters:

- model identity helps explain why two goals with similar titles or task types behaved differently
- it makes cost comparisons more trustworthy by separating model effects from workflow effects
- it helps detect when a cheaper model is not actually cheaper because it increases retry pressure

## Scope

In scope:

- schema extension for model identity on goals and entries
- CLI mutation flow support for storing model identity
- telemetry sync support when model data is available
- summary and report output grouped by model where the data is trustworthy
- validation rules
- tests
- backward compatibility for older metrics files without model fields

Out of scope:

- provider-specific model adapters in the public CLI
- automatic reconstruction of historical model data from logs when it is missing
- detailed model benchmarking dashboards
- changing the `mini-first` policy experiment itself

## Functional Requirements

### 1. Source-of-truth schema

Add an optional `model` field to stored goal and entry records.

Rules:

- field is optional for backward compatibility
- when present, it must be a non-empty string after trimming
- the stored value should be the canonical model identity used for analysis, not a decorative label
- historical records without model data must still load successfully

### 2. Entry-level persistence

Attempt entries are the source of truth for per-attempt model usage.

When a goal mutation or sync event knows the model used for a specific attempt:

- persist that model on the attempt entry
- continue computing cost and token totals as today
- keep the model value attached to the exact attempt that used it

This is important because a goal may be retried with a different model later.

### 3. Goal-level summary

Goal records should expose a summary model only when it is unambiguous.

Recommended rule:

- if all known entries for the goal use the same canonical model, store that model on the goal record too
- if the goal spans multiple models, do not force a misleading single goal-level model
- mixed-model goals should remain analyzable through entry-level history and an explicit mixed flag or equivalent summary signal

The goal-level field is a convenience summary, not a replacement for the attempt-level record.

### 4. Reporting and aggregation

Add model-aware summaries so the agent can compare outcomes by model.

At minimum, the reporting surface should expose:

- how many closed goals have a known model
- how many closed goals are mixed-model goals
- model-specific success / failure / attempt counts
- model-specific cost and token totals where coverage is sufficient

If a goal is mixed-model, reporting should not silently assign the whole goal to one model bucket unless that assignment is clearly labeled as an attempt-level slice.

### 5. CLI visibility

Update `show` and markdown export so model identity is visible without raw JSON inspection.

Minimum display expectations:

- show model on a goal when it is known
- show model on an attempt when it is known
- surface model coverage or mixed-model warnings in summary output
- make it obvious when data is only partially covered

## Data Model Requirements

Update the domain layer to support model identity on:

- `GoalRecord`
- `AttemptEntryRecord`
- `EffectiveGoalRecord`

Recommended behavior for the effective record:

- `model` should be populated only when the model is known and consistent for the whole goal chain
- `model_complete` should indicate that all relevant records in the chain have a model
- `model_consistent` or a similar flag should indicate whether the chain uses one model or multiple models
- mixed-model chains should remain represented without inventing a single false label

Compatibility requirement:

- existing metrics files without the new field must continue to load successfully

## CLI Requirements

Additive behavior only.

The update flow should:

- accept a model value when the user already provides one for pricing or telemetry-derived usage
- persist it alongside the attempt that produced the usage
- preserve existing `--model` behavior for cost computation
- keep current commands working for older records

Do not:

- require a new public parameter just to keep history usable
- break existing command flows or historical metrics files
- silently change model labels in a way that makes comparisons unstable

## Reporting Requirements

The resulting analysis should remain agent-first.

Reporting should help answer:

- which model is best for a given task class
- whether a cheaper model saves money or just shifts cost into retries
- whether mixed-model goals are common enough to matter

Avoid overloading the report with decorative model tables.
The model breakdown should support decisions, not become noise.

## Validation Requirements

At minimum, add or update automated tests for:

1. happy path persistence of model identity on new goal and entry records
2. backward compatibility loading older metrics files without model fields
3. invalid-state rejection for blank or non-string model values
4. mixed-model goal handling without a misleading goal-level summary
5. summary / report consistency after mutation
6. telemetry sync or usage ingestion preserving the model when available

## Suggested Implementation Plan

1. Extend domain dataclasses, parsing, serialization, defaults, and validation.
2. Add model persistence to goal mutation and attempt-entry mutation paths.
3. Update telemetry sync or usage ingestion so model identity is preserved when available.
4. Add model-aware summary and reporting output.
5. Add regression tests for compatibility, mixed-model behavior, and summary consistency.
6. Run local verification and a CLI smoke test against regenerated metrics.

## Acceptance Criteria

The feature is done when:

1. new and updated attempts can persist the model used
2. goal records surface a model only when the model is unambiguous
3. mixed-model goals are represented without lying about a single model
4. summary output exposes model coverage and model-based breakdowns
5. old metrics files still load and validate
6. relevant automated tests pass
7. CLI smoke checks pass

## Risks

- provider model labels may be inconsistent across sources
- a goal that mixes models may be harder to summarize cleanly than a single-model goal
- model-only reporting could distract from the quality-first framing if not kept secondary

## Guardrails

- preserve quality-first reporting over cost-only optimization
- use explicit coverage and mixed-model language instead of guessing
- keep the public contract agent-agnostic
- do not force a single model label when the history does not support it

## Open Questions For Implementation

- should the stored model be the raw provider model string, the normalized pricing model, or both
- if both are needed later, what should the canonical public field be
- whether model grouping should happen only at the goal level, only at the attempt level, or in both views
