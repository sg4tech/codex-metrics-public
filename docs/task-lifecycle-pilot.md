# Task Lifecycle Pilot

## Purpose

This document describes a lightweight pilot workflow for running Codex-assisted engineering through explicit task stages instead of ad hoc conversational jumps.

The goal is not to add bureaucracy.

The goal is to improve:

- outcome fidelity
- operator control
- handoff clarity
- reviewability
- cost and quality attribution by phase

This is a pilot operating model, not yet a required repository-wide rule.

## Why Try This

The current system already tracks:

- goals
- attempts
- reviewed result fit
- retry pressure
- cost and token signals

But the history still shows a recurring weakness:

- some misses came from doing adjacent work instead of the requested outcome
- some unclear outcomes came from jumping between analysis, implementation, review, and PM framing without a clear stage boundary

This pilot is meant to test whether a clearer lifecycle improves quality without making the workflow too heavy.

## Core Idea

Use one task with an explicit current stage.

The lead is the only orchestration point.

That means:

- requests enter through the lead
- stage transitions are decided by the lead
- delivery work happens only inside the current stage
- the operator does not silently switch the task into a different mode of work

## Roles

### Lead

The lead is responsible for:

- interpreting the request
- deciding whether the request should become a new task or continue an existing one
- setting the current stage
- deciding when a stage is complete
- requesting the next stage
- deciding whether the outcome is accepted, needs rework, or should fail

### Implementer

The implementer is responsible for:

- executing the current stage
- reporting findings and blockers clearly
- not expanding the task into a different stage without an explicit handoff
- keeping the work aligned to the requested outcome rather than adjacent technical improvements

### Reviewer / QA / Client

These may be separate humans or may be represented by the same operator in different roles.

The important part is not role purity.

The important part is that acceptance and handoff points become explicit.

## Recommended Stages

Use the smallest set that still clarifies the work:

1. `requirements`
2. `analysis`
3. `implementation`
4. `code_review`
5. `qa`
6. `demo`
7. `retro`

Not every task must spend a long time in every stage.

Small tasks may pass through several stages quickly.

The purpose of the stages is to make the current mode of work explicit, not to slow simple tasks down.

## Stage Definitions

### `requirements`

Goal:

- clarify what outcome is actually wanted

Exit criteria:

- request is specific enough to judge success later
- obvious ambiguities are resolved
- scope is small enough to execute

Do not leave this stage with:

- vague acceptance criteria
- unresolved “maybe this is what was meant” assumptions

### `analysis`

Goal:

- understand current behavior, constraints, likely root cause, and viable options

Exit criteria:

- current state is understood
- the bottleneck is identified or narrowed
- a recommended approach exists

Do not leave this stage with:

- implementation started before the problem is understood
- polishing of non-constraints

### `implementation`

Goal:

- make the smallest useful change that addresses the agreed problem

Exit criteria:

- change is implemented
- relevant tests and validations are updated

Do not leave this stage with:

- large adjacent improvements that were not requested
- unverified code presented as done

### `code_review`

Goal:

- look for defects, regressions, broken invariants, and missing coverage

Exit criteria:

- significant findings are either fixed or explicitly accepted as follow-up

Do not treat this stage as:

- a rewrite opportunity
- a style-polishing pass without risk reduction

### `qa`

Goal:

- verify the behavior actually works through the strongest practical automated checks

Exit criteria:

- relevant automated verification passes
- runtime or E2E checks are done where they materially reduce uncertainty

### `demo`

Goal:

- present the result in user-facing terms and confirm it matches the intended outcome

Exit criteria:

- accepted
- or sent back for rework

This is where “technically done but not what was wanted” should surface.

### `retro`

Goal:

- capture what worked, what failed, and what should become a permanent rule, test, or guardrail

Exit criteria:

- the lesson is classified correctly:
  - code
  - test
  - local rule
  - reusable policy
  - retrospective only

## Operating Rules

### One task, one current stage

Avoid mixing multiple active stages in the same moment.

Bad pattern:

- requirements drift during implementation
- code review happens while analysis is still incomplete
- demo framing changes what “done” means after implementation is already being judged

### Lead-only stage transitions

The implementer should not silently upgrade:

- analysis into implementation
- implementation into acceptance
- review into PM/product reframing

If the work needs to move stages, call that handoff explicitly.

### Use the current metrics model, not a new schema yet

For the pilot, do not add a new task engine immediately.

Use the current goal-based system and treat stage as an operational overlay recorded in notes, titles, or explicit handoff comments.

Only automate this if the manual flow proves useful.

### Keep product goals outcome-oriented

Do not create separate product goals for every stage by default.

Prefer:

- one outcome-oriented product goal
- multiple attempts or notes across stages

Create a new linked goal only when the outcome itself changes, is superseded, or restarts.

## Suggested Manual Pilot Flow

1. Lead defines the task and current stage.
2. Implementer works only inside that stage.
3. Lead decides the next stage.
4. Repeat until demo/acceptance.
5. Finish with a short retro.

Minimal handoff note template:

- current stage
- what is now known
- what remains uncertain
- what decision is needed to move forward

## What To Measure During The Pilot

Do not over-instrument yet.

Just watch for these signals:

- fewer adjacent or off-target outcomes
- fewer unclear-task misses
- cleaner acceptance decisions
- fewer “we solved a different problem” cases
- better ability to explain where time and cost were spent

## When To Automate This In The Tool

Automate only if the pilot shows real value.

Good reasons to add explicit lifecycle support later:

- stage transitions are repeatedly useful
- stage-specific delays or rework become important signals
- the lead workflow is stable enough to encode

Bad reasons:

- the process merely sounds more professional
- the team wants stronger structure before proving the pilot helps
- the workflow is still changing every few tasks

## Recommendation

Start with a manual pilot on a small number of real tasks.

If it improves outcome fidelity and decision quality without creating too much overhead, then add lightweight stage support to the CLI and reporting later.
