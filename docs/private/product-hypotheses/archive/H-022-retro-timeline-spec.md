# Feature Spec: Retrospective Timeline Analysis For Before/After Product Metrics

## Status

- Draft date: `2026-04-03`
- Owner: `product / metrics`
- Intended audience: `development team`
- Related hypothesis: [H-022](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-022.md)

## Problem

The current repository can already do two weaker things:

- store final structured outcomes in the metrics ledger
- reconstruct historical conversations, attempts, and usage from local Codex history

That is enough to say that retros exist and that product outcomes exist, but it is not enough to answer the more useful question:

- what changed in later product metrics after a specific retrospective happened

The current `retro/meta` hypothesis is still too coarse because same-day or same-period aggregates do not model the sequence that matters:

1. product metrics before a retrospective
2. the retrospective event itself
3. product metrics after that retrospective
4. the next retrospective or workflow intervention on the same timeline

Without an explicit timeline layer, an analyzing agent still has to reconstruct these sequences manually.

## Goal

Build a read-only retrospective timeline analysis layer that:

- detects or loads retrospective events as time anchors
- computes comparable product-metric windows around each anchor
- stores the resulting before/after dataset for later analysis
- helps an analyzing agent ask “what changed after this retro?” without manual reconstruction

The first version should optimize for a trustworthy analysis dataset, not for proving causal effect by itself.

## Non-Goals

This feature should not:

- claim that retrospectives are already proven to help
- mutate `metrics/codex_metrics.json`
- automatically classify retrospective impact as positive or negative with high confidence
- require live browser/manual analysis to be useful
- solve every intervention-analysis problem before a narrow retro-focused version exists

## Product Intent

The product should move from:

- “we think retros help”

to:

- “here are the metric windows before and after each retrospective event”
- “here are the failure modes or quality metrics that moved afterward”
- “here is the dataset an analyzing agent can use for later statistical work”

This keeps the system honest: first build the intervention timeline, then let analysis argue about significance.

## Scope

In scope for the first implementation:

- retrospective event extraction from the existing ledger/history surface
- time-ordered retro anchors for the current repository
- product-metric windows before and after each retrospective
- a read-only analysis table or SQLite mart for those windows
- one CLI/reporting surface to inspect the resulting dataset
- automated tests for event extraction, window construction, and summary stability

Out of scope for the first implementation:

- automatic causal claims
- live intervention tagging during the conversation
- generalized support for every possible workflow intervention
- complex statistical modeling built into the CLI
- mutation of the source-of-truth metrics ledger

## Target User

Primary user:

- AI agents that analyze product/workflow history

Secondary user:

- the human sponsor who later receives the synthesized conclusions

Why this is useful:

- the agent gets a concrete temporal dataset instead of vague retrospective lore
- the agent can compare windows without hand-building them in each analysis
- later statistical analysis can reuse a stable extracted table instead of re-deriving anchors and windows ad hoc

## Proposed Analysis Model

### Core timeline sequence

The model should treat history as an ordered sequence of:

- product-goal outcomes and timestamps
- retrospective events and timestamps
- optional other intervention markers later

The core unit is:

- `metric window before` -> `retro event` -> `metric window after`

### Anchor definition

The first anchor type is:

- `retro_event`

An anchor should represent a retrospective that is visible in repository history, ideally from one or more of:

- a closed ledger goal with `goal_type = retro`
- a file created or updated in `docs/retros/`
- retrospective text in reconstructed history that can be linked back to the goal/thread

The first version should prefer stable repository-visible signals over weak transcript-only heuristics.

### Window definition

The default window should be outcome-count-based rather than calendar-based.

Recommended first rule:

- `N` closed `product` goals before the retro event
- `N` closed `product` goals after the retro event

This is preferable to calendar days because local work volume is irregular.

The first implementation should support at least one fixed default such as:

- `N = 5`

It may later support:

- `N = 10`
- time-based windows
- failure-mode-specific windows

### Metrics per window

Each window should compute a small, defensible set of product metrics:

- `product_goals_closed`
- `product_success_rate`
- `exact_fit_rate`
- `partial_fit_rate`
- `miss_rate`
- `attempts_per_closed_product_goal`
- `known_cost_per_success_usd`
- `known_cost_coverage`
- `failure_reason_counts` or a compact structured summary

The first version should prefer explicit coverage fields whenever the underlying data is partial.

## Data Model

The feature should persist or emit a dataset shaped roughly like this.

### `retro_timeline_events`

One row per retrospective anchor.

Suggested fields:

- `retro_event_id`
- `goal_id` or `thread_id` when resolvable
- `event_time`
- `event_date`
- `project_cwd`
- `title`
- `summary`
- `failure_mode`
- `proposed_change`
- `source_kind` such as `ledger`, `retro_file`, or `history`
- `raw_json`

### `retro_metric_windows`

One row per metric window around a retrospective.

Suggested fields:

- `window_id`
- `retro_event_id`
- `window_side` as `before` or `after`
- `window_strategy` such as `product_goals_count`
- `window_size`
- `anchor_time`
- `window_start_time`
- `window_end_time`
- `product_goals_closed`
- `exact_fit_rate`
- `partial_fit_rate`
- `miss_rate`
- `attempts_per_closed_product_goal`
- `known_cost_per_success_usd`
- `known_cost_coverage`
- `failure_reason_summary`
- `raw_json`

### `retro_window_deltas`

One row per retrospective event with before/after comparisons.

Suggested fields:

- `retro_event_id`
- `window_strategy`
- `window_size`
- `before_product_goals_closed`
- `after_product_goals_closed`
- `delta_exact_fit_rate`
- `delta_partial_fit_rate`
- `delta_miss_rate`
- `delta_attempts_per_closed_product_goal`
- `delta_known_cost_per_success_usd`
- `delta_known_cost_coverage`
- `raw_json`

The exact schema can change, but the product contract should preserve the three conceptual layers:

- anchor event
- metric windows
- before/after delta

## Functional Requirements

### 1. Retrospective event extraction

The system should be able to build a stable list of retrospective anchors for the current repository.

At minimum, it should support:

- ledger goals with `goal_type = retro`
- repository retrospective files in `docs/retros/`

If both exist for the same retro, the feature should prefer a single merged anchor rather than duplicate anchors.

### 2. Ordered timeline

The anchors must be stored in time order and remain attributable to the repository/workspace slice they came from.

### 3. Comparable windows

For each retrospective anchor, the system should compute at least one `before` and one `after` window using the same strategy and size.

### 4. Product-only metric focus

The window metrics should focus on later `product` outcomes, not blend `product`, `retro`, and `meta` into one number.

### 5. Partial-data honesty

If cost coverage, result-fit coverage, or failure-reason coverage is incomplete inside a window, the output must say so explicitly.

### 6. Read-only behavior

The feature must not mutate the ledger. It is an analysis surface only.

### 7. Reviewable output

An analyzing agent should be able to inspect:

- which retro was used as the anchor
- which goals fell into the before/after windows
- which metrics were computed
- which fields are complete versus partial

## Suggested Extraction Strategy

### Stage 1: Stable anchor inventory

Build a deterministic list of retrospective anchors from the ledger and `docs/retros/`.

Prefer:

- explicit repository artifacts

over:

- loose transcript heuristics

### Stage 2: Goal-window selection

For each anchor, select the nearest `N` closed product goals before and after the anchor time.

### Stage 3: Window metrics

Compute the selected product metrics for each side.

### Stage 4: Delta layer

Store the before/after comparison as an explicit output row rather than making each analysis recompute it.

### Stage 5: Reporting surface

Add a CLI or report surface that can render:

- the anchor inventory
- the window metrics
- the deltas

## Validation Requirements

At minimum, add or update automated tests for:

1. deterministic extraction of retrospective anchors from a mixed ledger/history sample
2. stable ordering of anchors on the timeline
3. correct before/after product-goal window selection around an anchor
4. honest handling of incomplete cost or fit coverage
5. read-only behavior with no mutation of `metrics/codex_metrics.json`
6. stable delta calculation for a fixture with known expected values

## Acceptance Criteria

The feature is useful when:

1. the repository can produce a stable list of retrospective timeline anchors
2. each anchor has at least one comparable before/after product-metric window
3. the output makes coverage and partial-data limits explicit
4. an analyzing agent can inspect “what changed after this retro?” without manual reconstruction
5. the resulting dataset is stable enough to reuse in later statistical analysis

## Risks

- retrospective timestamps may be ambiguous when ledger and file history disagree
- nearby retros may create overlapping windows that complicate interpretation
- low product-goal volume around some retros may make windows too small to be useful
- a timeline dataset may still be observational rather than causal

## Guardrails

- prefer stable repository-visible anchors over inferred chat-only anchors
- keep the output read-only
- keep coverage fields explicit
- prefer count-based windows before time-based windows
- do not present deltas as proof of causality

## Open Questions For Implementation

- what is the canonical timestamp when ledger close time and retro file mtime differ
- should the first implementation require both a `retro` goal and a retro file, or allow either
- what default window size gives enough signal without excessive overlap
- should windows exclude goals that explicitly belong to a different project slice in a workspace-wide warehouse
- should the first CLI output be table-like, JSON-first, or both

## Suggested Implementation Plan

1. Define the canonical retrospective anchor rules from ledger and `docs/retros/`.
2. Add a derived retro-timeline store or mart in the history/analysis layer.
3. Implement product-goal window selection around each anchor.
4. Compute before/after metrics plus explicit coverage fields.
5. Add a read-only CLI/report command for the dataset.
6. Add fixture tests for anchor extraction, window selection, and delta stability.
7. Revisit [H-015](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-015.md) once the timeline dataset exists.
