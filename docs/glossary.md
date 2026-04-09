# Glossary

This glossary is for future agents working on ai-agents-metrics. It uses the repository's current semantics, even where the code still carries legacy task-oriented names.

### active goal

A goal with `status="in_progress"`; the FSM treats any nonzero count of such goals as `ACTIVE_GOAL_EXISTS`, even though the intended operating model is a single active goal at a time.

### attempt / entry

These are the same unit of work at different layers: an `attempt` is the conceptual retry or execution pass, while an `entry` is the stored `entries[]` record for that pass.

### AttemptEntryRecord

The stored dataclass for one attempt row in the event log, keyed by `entry_id` and linked back to its parent `GoalRecord` through `goal_id`.

### by_goal_type / by_task_type

These are aliases for the same nested summary dictionary, with `by_task_type` kept as a legacy name for `by_goal_type`.

### closed goal

A goal whose `status` is `success` or `fail`; `closed` is a lifecycle concept, not a separate status value.

### EffectiveGoalRecord

The derived, non-persisted view of a goal chain after following `supersedes_goal_id` back to the earliest linked goal and aggregating costs, tokens, timestamps, and model consistency across the chain.

### goal

The canonical stored unit of work in the event log; `task` is the older and more conversational alias still used in CLI flags, helper names, and legacy data paths.

### goal_type

The stored classification for a goal, with `product` for delivery work, `retro` for retrospective analysis and writeups, and `meta` for bookkeeping, policy, audit, tooling, and support work.

### GoalRecord

The stored dataclass for one goal in the event log; it holds the raw per-goal fields before any supersession-chain aggregation is applied.

### history pipeline

The three-stage transcript workflow: `ingest` loads raw Codex sources into the SQLite warehouse, `normalize` cleans and standardizes those raw tables, and `derive` builds higher-level marts such as goals, attempts, retry chains, and timeline events.

### inferred entry

An `AttemptEntryRecord` with `inferred=true`, meaning the row was synthesized during history reconstruction in the history pipeline or auto-closed when a newer attempt started, rather than captured as an explicit user-visible attempt record.

### event log

The append-only NDJSON file at `metrics/events.ndjson`. Each CLI command appends one JSON line (an event). State is reconstructed at read time by replaying all events in file order, last-write-wins per `goal_id` / `entry_id`. It is the canonical metrics store.

### known vs complete coverage

`known_*` counts mean some data exists for a successful goal, while `complete_*` counts mean every goal in the supersession chain has that data; the split exists so partial coverage can be reported without pretending it is full coverage.

### model

The model name attached to a goal or attempt record when it is known; it is aggregated into `model_complete_goals` and `mixed_model_goals` so the summary can distinguish goals with a single consistent model from goals whose attempts used different models.

### result_fit

The product-only quality label for how well the delivered outcome matched the request, with `exact_fit`, `partial_fit`, or `miss`; it is separate from `status`, so a successful product goal may still be only a `partial_fit`.

### source of truth

`metrics/events.ndjson` is the authoritative metrics store; the markdown report is an export, not the canonical record, and replayed event state wins if anything else disagrees.

### summary block

The computed aggregate under `summary` in replayed metrics state, including nested per-type and per-model rollups; it is regenerated from stored goals and entries and is never edited by hand.

### supersedes / supersedes chain

`supersedes_goal_id` points from a newer goal to the closed goal it replaces, and the supersession chain is the linked sequence you get by following those pointers back to the earliest goal in the retry history.

### task

A legacy synonym for `goal` that persists in CLI names, parser flags, policy language, and the old `tasks` alias in historical data; in the current schema, tasks are stored as goals.

### warehouse

The intermediate SQLite cache used by the history pipeline, living under `.ai-agents-metrics/` and holding raw, normalized, and derived tables for transcript analysis rather than the primary JSON metrics store.

### WorkflowEvent

The CLI event enum that drives workflow transitions: `start-task`, `continue-task`, `finish-task(success)`, `finish-task(fail)`, `update(create)`, `update(close)`, `update(repair)`, `ensure-active-task`, and `show`.

### WorkflowState

The workflow FSM state enum: `CLEAN_NO_ACTIVE_GOAL` means no active goal and no detected started work, `STARTED_WORK_WITHOUT_ACTIVE_GOAL` means work is underway without a bookkeeping goal, `ACTIVE_GOAL_EXISTS` means at least one active goal is present, `CLOSED_GOAL_REPAIR` is the repair-only path for closed-goal mutations, and `DETECTION_UNCERTAIN` means the detector could not reliably tell what state the repo is in.
