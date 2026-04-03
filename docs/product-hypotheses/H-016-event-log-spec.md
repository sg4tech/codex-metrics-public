# Feature Spec: Minimal Structured Event Logging For Workflow Decisions

## Status

- Draft date: `2026-04-03`
- Owner: `product / metrics`
- Intended audience: `development team`
- Related hypothesis: [H-016](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-016.md)

## Problem

The repository already records final goal state, but that is not enough to explain whether a workflow change actually changed behavior.

We need a narrow event layer that can answer:

- which CLI command was invoked before the workflow started changing state?
- did the workflow recover from a blocked state?
- did the guardrail reject a mutation or a bad continuation?
- did the event store itself fail to write?
- did the event stream reveal a transition that goal status alone would hide?

## Goal

Add a minimal, durable event vocabulary that supports the first useful product questions without becoming a second copy of the goal ledger.

The first version should optimize for trust and observability, not coverage.

## Non-Goals

This feature should not:

- replace `metrics/codex_metrics.json` as the source of truth
- model every possible workflow event on day one
- infer causal impact automatically
- depend on manual debug notes as the primary data source
- introduce provider-specific public flags or workflows

## First Event Families

Start with only these families:

- `cli_invoked`
- `goal_created`
- `goal_updated`
- `goal_attempt_incremented`
- `goal_closed`
- `goal_merged`
- `usage_synced`
- `observability_write_failed`

These should be enough to anchor the first before/after analysis and detect whether the observability layer is carrying its weight.

## Minimum Payload Expectations

Each event should record:

- `event_type`
- `goal_id` when applicable
- `goal_type` when applicable
- `command`
- `cwd` for CLI invocation events
- `status_before` and `status_after` when applicable
- `attempts_before` and `attempts_after` when applicable
- `result_fit_before` and `result_fit_after` when applicable
- a compact JSON payload with the changed fields or reason for the event

## Acceptance Criteria

The first pass is useful when all of the following are true:

- the event store persists the first event families above
- the top-level CLI dispatch records `cli_invoked` before any workflow mutation handler runs
- the debug log mirrors the stored event in a human-readable form
- event writes fail best-effort without breaking goal mutation
- the event vocabulary can support H-022-style before/after analysis without restating only goal status
- tests cover at least one happy path and one write-failure path

## Relationship To Other Work

- H-016 defines why the event layer exists
- H-018 can supply transcript-derived candidates for future event families
- H-022 can consume these events as timeline anchors for before/after windows
