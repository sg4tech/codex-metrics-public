# Feature Spec: Persist Input / Output / Cached Token Breakdown

## Status

- Draft date: `2026-04-02`
- Owner: `product / metrics`
- Intended audience: `development team`
- Related hypothesis: [H-009](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-009.md)

## Problem

`codex-metrics` currently computes usage cost from separate `input_tokens`, `output_tokens`, and `cached_input_tokens`, but stores only:

- `cost_usd`
- `tokens_total`

This loses the shape of usage after pricing is computed.

As a result, agent-facing analysis can tell that a task was expensive, but cannot reliably answer:

- Was the cost driven mostly by prompt/input size?
- Was it driven mostly by verbose output?
- Did cache reuse improve or regress?
- Did a workflow change reduce total tokens by shifting cost from one side to another?

For an agent-first metrics product, this is a meaningful observability gap.

## Goal

Add first-class persisted token-breakdown fields so the source-of-truth metrics file can preserve:

- `input_tokens`
- `output_tokens`
- `cached_input_tokens`

at both:

- goal level
- attempt-entry level

and expose rolled-up summaries that let analyzing agents reason about token mix, not only total volume.

## Expected Product Outcome

After this feature, an analyzing agent should be able to answer:

1. whether cost waste is primarily input-side, output-side, or cache-efficiency related
2. whether a workflow change reduced total cost through healthier token mix instead of only smaller total volume
3. whether product success quality is being preserved while token-shape efficiency improves

## Non-Goals

This feature should not:

- change the quality-first product framing
- optimize for lower token counts at the expense of outcome fit
- require perfect historical backfill before shipping
- introduce hosted analytics or dashboards
- replace `tokens_total`; it should remain for compatibility and quick top-line reporting

## User Value

Primary user:

- AI agents that analyze metrics and recommend workflow changes

Secondary user:

- human sponsor who receives the final synthesized analysis

Why this is valuable:

- agents need diagnosis-friendly cost data, not just blended totals
- separate token categories make optimization suggestions more trustworthy and less guess-based
- cache-aware usage can become an explicit signal instead of hidden implementation detail

## Scope

In scope:

- metrics schema extension for token-breakdown fields
- CLI update flow support for explicit token-breakdown inputs
- Codex telemetry sync persistence of token breakdown
- summary aggregation for input/output/cached totals and coverage
- report and `show` output updates
- validation rules
- tests
- migration behavior for existing files with missing breakdown fields

Out of scope:

- retroactive perfect reconstruction for every historical goal
- any product framing changes beyond recording the hypothesis and exposing the new metric surface
- pricing-model redesign beyond existing per-model pricing behavior

## Functional Requirements

### 1. Source-of-truth schema

Extend stored goal records and entry records to support nullable fields:

- `input_tokens`
- `output_tokens`
- `cached_input_tokens`

Rules:

- fields are optional for backward compatibility
- values must be non-negative integers when present
- `tokens_total` remains supported
- when all three token-breakdown fields are known for a record, `tokens_total` must equal their sum

### 2. Usage ingestion

When usage is provided via CLI flags or recovered from Codex telemetry:

- persist the token breakdown fields
- continue computing `cost_usd` using the pricing config
- continue populating `tokens_total`

If only partial usage exists:

- preserve what is known
- do not invent missing token categories
- mark totals and summaries consistently with partial coverage semantics already used by the product

### 3. Goal and entry mutation behavior

For updates that add usage:

- breakdown fields should accumulate consistently with current `cost_usd` and `tokens_total` behavior
- attempt entry deltas should preserve the per-attempt token breakdown where it can be derived
- sync flows should update stored breakdown fields when telemetry data is available

### 4. Summary reporting

Add summary totals, at minimum:

- `total_input_tokens`
- `total_output_tokens`
- `total_cached_input_tokens`

Add covered-success views parallel to existing known/complete cost logic where practical:

- known breakdown coverage for successful goals
- complete breakdown coverage for successful goals only when all relevant token fields are present

At minimum, the reporting surface should let agents compare:

- total tokens
- input share
- output share
- cached-input share

### 5. CLI and report visibility

Update `show` and markdown reporting so the new fields are visible without requiring raw JSON inspection.

Minimum display expectations:

- top-level totals for input/output/cached/total
- per-goal token breakdown when present
- coverage messaging when historical breakdown data is partial

## CLI Requirements

Additive behavior only.

Potential interface shape:

- continue supporting `--model`, `--input-tokens`, `--output-tokens`, and `--cached-input-tokens`
- extend persistence so these fields are not collapsed into totals only
- keep existing `tokens_total` and cost flags working

Do not:

- break existing commands or historical metrics files
- require users to provide all token fields if only some are known

## Data Model Requirements

Update domain records and validation logic to support the new fields on:

- `GoalRecord`
- `AttemptEntryRecord`
- `EffectiveGoalRecord`

Update aggregation logic so effective goals and summary blocks can represent:

- known totals
- complete coverage
- rolled-up breakdown totals

Compatibility requirement:

- existing metrics files without the new fields must continue to load successfully

## Reporting Requirements

The resulting analysis should remain agent-first.

Reporting should help answer:

- where the token load is concentrated
- whether cache reuse is materially helping
- whether the cost mix changed after a workflow/process change

Avoid overloading the report with decorative breakdown noise.
The breakdown should support decisions, not become a vanity table.

## Validation Requirements

At minimum, add or update automated tests for:

1. happy path persistence of explicit input/output/cached fields
2. cost computation consistency when breakdown fields are provided
3. sync from Codex telemetry storing breakdown fields as well as totals
4. backward compatibility loading old metrics files without breakdown fields
5. invalid-state rejection for negative values
6. invalid-state rejection when `tokens_total` conflicts with the known breakdown sum
7. summary/report consistency after mutation

## Suggested Implementation Plan

1. Extend domain dataclasses, parsing, serialization, defaults, and validation.
2. Extend goal/entry aggregation and summary structures.
3. Update CLI mutation and sync flows to persist breakdown values.
4. Update reporting output for JSON-derived summaries and per-goal display.
5. Add regression tests covering compatibility and invariants.
6. Run full local verification and a CLI smoke flow against regenerated metrics.

## Acceptance Criteria

The feature is done when:

1. new and updated goals can persist `input_tokens`, `output_tokens`, and `cached_input_tokens`
2. automatic Codex usage sync writes those fields when telemetry provides them
3. `tokens_total` and `cost_usd` remain correct
4. summary output exposes aggregate token breakdown totals
5. old metrics files still load and validate
6. relevant automated tests pass
7. CLI smoke checks pass

## Risks

- telemetry coverage may be incomplete for some historical or current sessions
- additive schema growth may complicate reporting if not kept simple
- users may misread token-reduction as product improvement when quality stays unmeasured

## Guardrails

- preserve `tokens_total` as a stable compatibility field
- keep quality-oriented reporting primary over cost-only optimization
- use explicit coverage language whenever token breakdown is partial
- fail loudly on contradictory stored usage data

## Open Questions For Implementation

- whether breakdown coverage should be tracked with dedicated summary counters or derived on demand
- whether attempt-entry delta reconstruction needs separate helper logic for breakdown fields
- whether markdown report output should show percentages, raw totals, or both

## Recommended Delivery Slice

Ship as one additive vertical slice:

- schema
- sync/update persistence
- reporting
- tests

Do not split reporting away from storage, because the product value of the feature depends on agents being able to see and use the new fields immediately after they are stored.
