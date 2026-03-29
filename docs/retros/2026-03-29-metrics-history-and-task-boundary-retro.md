# Metrics History And Task Boundary Retro

## Situation

The project discovered that the metrics history had been overstating success.

One product goal, fully automatic cost tracking, was first recorded as a successful pricing workflow and only later corrected after it became clear that the first version still required manual or semi-manual usage input. That created two connected problems:

- one rejected attempt was incorrectly counted as `success`
- one coherent product goal was split across separate task records instead of being represented as one task with multiple attempts

## What Happened

- The metrics workflow and updater were introduced and then hardened over several small tasks.
- Cost tracking was first implemented as pricing math plus manual usage inputs.
- That implementation was technically valid in isolation, but it did not satisfy the real product requirement of fully automatic tracking.
- The initial cost-tracking task was recorded as `success` anyway.
- A later review surfaced the mismatch because the report still showed mostly `cost_usd: null` and `tokens_total: null`.
- The real solution shifted to automatic ingestion from local Codex SQLite telemetry.
- After that product correction, the task history still looked too optimistic until the earlier pricing-only task was manually reclassified to `fail`.
- A dedicated `merge-tasks` command was then added so that future split-history corrections can be done through the updater instead of manual JSON edits.

## Root Cause

The core failure was not bad math or broken code. The deeper problem was premature success classification under fuzzy task boundaries.

The project treated an intermediate technical milestone as if it were the product outcome itself. Once that happened, the metrics layer faithfully recorded the wrong story.

## 5 Why

### Problem

Why did the metrics history overstate success and split one product goal across multiple tasks?

### Why 1

Because the pricing-only implementation was marked `success` even though the user requirement was fully automatic cost tracking.

### Why 2

Because completion was judged at the level of "the script can now calculate price" instead of "the product can now track price automatically in real usage."

### Why 3

Because task boundaries were defined around implementation chunks rather than the user-visible outcome.

### Why 4

Because the workflow had rules for statuses, attempts, and validation, but it did not yet have an explicit operational rule for how to classify:

- an intermediate milestone that is technically correct but not yet acceptable
- a refinement that is actually a retry of the same product goal rather than a new task

### Why 5

Because the project optimized early for bookkeeping mechanics and script safety, but not yet for semantic discipline around outcome definition.

In other words, the tooling matured faster than the decision rule for what counts as one task and what counts as success.

## Retrospective

This is a healthy kind of failure because it exposed a subtle but important truth: reliable metrics are not only about correct arithmetic and strict schemas. They also depend on correct task semantics.

The updater already became fairly strong at validation, summary recomputation, safe file generation, pricing, and telemetry ingestion. But none of that can protect the accuracy of the metrics if a product goal is split incorrectly or a milestone is promoted to `success` too early.

The correction path was also informative:

- first the false `success` had to be reclassified to `fail`
- then the project needed a dedicated merge capability to repair split history safely

That is a sign that the project has moved from raw implementation into governance of measurement quality, which is the right next maturity step.

## Conclusions

- The hardest part of task metrics is often semantic classification, not storage.
- A technically correct intermediate result must not be marked `success` unless it satisfies the requested outcome.
- One product goal should stay one task unless the user clearly pivots to a new goal.
- If a second implementation pass exists because the first result was not accepted, that is usually another attempt on the same task, not a new success.
- Tooling should support repair of history, but the larger win is preventing classification drift before it happens.

## Permanent Changes

- Treat user acceptance of the requested outcome, not technical partial progress, as the success boundary.
- When a result is rejected but work continues toward the same product goal, prefer incrementing `attempts` on the same task instead of opening a fresh success candidate.
- Use `fail` plus `failure_reason` for rejected implementations instead of leaving the rejection implicit.
- Keep retrospective entries for metric-quality incidents, not only code or runtime incidents.
- Maintain repair tooling such as `merge-tasks`, but treat it as a guardrail rather than the default workflow.

## Solution Options

### Option 1: Process-only rule tightening

Add a documented rule to `AGENTS.md` and the policy that success is allowed only when the user-visible outcome is satisfied, and that rejected refinements of the same outcome stay on the same task as another attempt.

Pros:
- smallest change
- low implementation risk
- improves operator discipline immediately

Cons:
- still relies heavily on humans getting task boundaries right in the moment
- mistakes remain easy to make under time pressure

### Option 2: Add explicit task lifecycle commands

Introduce commands such as `start-task`, `attempt-failed`, `close-task-success`, and `close-task-fail`, making the workflow more opinionated and reducing room for semantic drift.

Pros:
- much clearer operator workflow
- easier to encode the intended state machine
- lower chance of accidental false success

Cons:
- larger CLI change
- may feel heavier than the current lightweight `update` workflow
- requires migration in habit and tests

### Option 3: Add semantic guardrails to `update`

Keep the current CLI, but add checks such as:

- warning or refusal when a new task title looks like a continuation of a recently failed or rejected one
- explicit `--continuation-of` or `--supersedes-task-id`
- optional prompt or hard check before marking success on tasks with no accepted outcome note

Pros:
- preserves backward compatibility better
- adds help exactly where mistakes happen
- can be introduced incrementally

Cons:
- heuristics may be imperfect
- guardrails reduce but do not eliminate semantic mistakes

### Option 4: Hybrid approach

Tighten the written process now and add one or two narrow semantic guardrails in the script, without fully redesigning the CLI.

Pros:
- best balance of speed and safety
- immediate behavior improvement without a large rewrite
- leaves room to evolve into a more opinionated workflow later

Cons:
- not as strong as a fully explicit lifecycle model
- still requires some judgment in ambiguous cases

## Recommendation

The best next step is Option 4.

The project is still small enough that a full lifecycle CLI would be more process than product, but large enough that process-only discipline is no longer sufficient. A hybrid approach gives the highest leverage:

- document a sharper success boundary
- document that rejected work on the same outcome stays one task with more attempts
- add a minimal semantic field or flag for continuation/supersession
- keep `merge-tasks` as a repair tool, not the normal path
