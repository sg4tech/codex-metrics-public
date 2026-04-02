# Feature Spec: Automatic Active-Task Enforcement

## Goal

Reduce late task-start bookkeeping by making `codex-metrics` detect missing active-task state and enforce or recover it automatically.

This feature exists because `start-task` being available as a command is not enough on its own. Real work can still begin before bookkeeping starts.

## Product Intent

The product should not rely on memory or discipline alone for one of its core invariants.

Desired outcome:

- once substantial work has started in a repository
- `codex-metrics` should be able to detect whether an active task exists
- and either:
  - fail loudly with a clear next step
  - or create a safe recovery draft

The external workflow contract must remain agent-agnostic.

This feature must not introduce provider-specific public commands or required parameters.

## Problem Statement

Current failure mode:

- meaningful implementation or documentation work can start
- no active `in_progress` goal exists yet
- bookkeeping is then created late, after progress already exists

Why this matters:

- `started_at` becomes less trustworthy
- timeline analysis becomes weaker
- retry and attempt history may be reconstructed after the fact instead of captured at the right time
- the product's own internal workflow becomes less credible

## Scope

In scope for the first implementation:

- detect when substantial repository work appears to have started without an active goal
- add a reusable active-task check in the CLI workflow
- support strict failure and explicit recovery
- keep the external command surface agent-agnostic
- add tests for happy path, false-positive control, and recovery

Out of scope for the first implementation:

- provider-specific session inspection
- Codex- or Claude-specific telemetry-based start detection
- background daemons or OS-level watchers
- fully automatic final task-title inference from natural-language chat history

## Core Design Constraint

Public API must remain universal.

That means:

- do not add new required public parameters for specific agents
- do not create separate public workflows for Codex vs Claude
- keep provider-specific logic behind internal detection or adapter layers

## Proposed Model

### Key Invariant

If substantial work has started in the repository, there should be an active `in_progress` goal unless the work is explicitly classified as not requiring task tracking.

### Active Goal Definition

An active goal is:

- a goal in `metrics/codex_metrics.json`
- with status `in_progress`
- and belonging to the current repository metrics file

### Started Work Heuristic

First implementation should use repository-local signals only.

Treat work as started when all of the following are true:

- no active `in_progress` goal exists
- repository has meaningful local changes
- at least one changed path is under tracked engineering surfaces such as:
  - `src/`
  - `tests/`
  - `docs/`
  - `scripts/`
  - top-level workflow files such as `AGENTS.md`, `README.md`, `Makefile`, `pyproject.toml`

First implementation should exclude obvious low-signal noise:

- cache directories
- compiled artifacts
- generated temporary files
- metrics/report outputs themselves when they are the only changed files

### Meaningful Local Changes

Use git-aware detection when the repo is inside git.

Accept these as signals:

- unstaged tracked changes
- staged changes
- newly added untracked files in meaningful surfaces

Do not count:

- ignored files
- deleted-only noise outside meaningful surfaces

## UX Modes

The first implementation should support two internal behavior modes:

### 1. Strict Guard

Behavior:

- if started work is detected and no active goal exists
- reject the relevant command with a clear error

Message should explain:

- work appears to have started without an active task
- why the command is being blocked
- how to recover

Example outcome:

- `Error: repository work appears to be in progress but no active goal exists; start or recover a task before continuing`

### 2. Explicit Recovery

Provide a recovery command that creates a safe draft active task.

Suggested command:

```bash
codex-metrics ensure-active-task
```

Behavior:

- if an active task already exists, print it and do nothing
- if no active task exists and no started work is detected, do nothing or explain that no recovery is needed
- if started work is detected with no active task, create a draft `in_progress` goal

Suggested default draft title:

- `Recover active task for in-progress repository work`

Suggested draft notes:

- explain that the task was auto-recovered because repository work was detected before task bookkeeping started

## Command Behavior

### New Command

Add:

```bash
codex-metrics ensure-active-task
```

Purpose:

- reusable workflow command for checking and recovering active-task state

### Existing Commands

First implementation should integrate active-task checking into:

- `continue-task`
- `finish-task`
- mutating `update` flows for existing goals

Optional for first implementation:

- `show` may emit a warning when started work is detected but no active goal exists

Do not enforce on:

- `init`
- `bootstrap`
- `show` as a hard failure
- `render-report`
- pure audit commands

### `start-task`

`start-task` remains valid.

But after this feature lands, `start-task` is no longer the only protection. It becomes:

- the clean proactive path

While `ensure-active-task` and strict guard behavior provide:

- detection
- enforcement
- recovery

## Data Model

No major schema expansion is required for the first step.

Optional addition:

- a note marker or structured note phrase indicating draft recovery origin

Do not add provider-specific public fields for this feature.

If recovery metadata later becomes valuable, consider one generic field such as:

- `bookkeeping_origin`

But that is not required for the first implementation.

## Technical Design

### New Internal Functions

Suggested internal helpers:

- `has_active_goal(data) -> bool`
- `detect_started_work(cwd: Path) -> StartedWorkReport`
- `ensure_active_task(data, cwd, metrics_path, ...) -> ActiveTaskResolution`

Suggested report structure:

- `started_work_detected: bool`
- `changed_paths: list[str]`
- `reason: str`

Suggested resolution structure:

- `status`: `existing` | `created` | `not_needed` | `blocked`
- `goal_id: str | None`
- `message: str`

### Git Integration

Prefer repository-local git inspection over ad hoc filesystem heuristics.

Suggested sources:

- `git status --porcelain`

Use it only to read repo state.

If git is unavailable or the repo is not under git:

- degrade safely
- do not guess aggressively
- return “cannot detect started work reliably” rather than inventing confidence

### Mutation Safety

Draft recovery must be:

- idempotent
- safe to rerun
- non-destructive

If one active goal already exists:

- do not create another one

If multiple active goals exist:

- fail loudly and require manual resolution

## Acceptance Criteria

The first implementation is complete when:

1. `codex-metrics ensure-active-task` exists and is documented in help text.
2. If started work is detected and no active goal exists, `ensure-active-task` creates one draft `in_progress` goal.
3. If an active goal already exists, `ensure-active-task` does not create duplicates.
4. Relevant mutating commands fail clearly when started work is detected and no active goal exists.
5. `show` can surface a warning about late bookkeeping candidates without failing.
6. The workflow remains agent-agnostic from the public CLI point of view.
7. Tests cover:
   - recovery creation
   - idempotent rerun
   - no-op when active goal exists
   - false-positive control for low-signal changes
   - strict rejection path
   - behavior outside git or with unavailable git

## Validation Plan

Minimum validation:

```bash
./.venv/bin/python -m pytest tests/test_update_codex_metrics.py
./tools/codex-metrics show
```

Preferred validation:

```bash
make verify
```

Additional smoke checks:

1. Start from a clean temp repo with initialized metrics.
2. Create a meaningful code or docs change without starting a task.
3. Run `codex-metrics ensure-active-task`.
4. Confirm one `in_progress` goal is created.
5. Re-run the command and confirm no duplicate goal is created.
6. Exercise a mutating command with no active goal and confirm strict rejection path works.

## Rollout Plan

### Phase 1

- implement internal started-work detection
- add `ensure-active-task`
- add strict rejection for the most relevant mutating commands
- add tests

### Phase 2

- add warning surfaces in `show` and audits
- refine meaningful-change heuristics
- reduce false positives

### Phase 3

- consider optional session-aware recovery hints
- only if the worktree-only approach proves insufficient

## Open Questions

- Should strict rejection apply to all mutating commands or only to the paths most likely to be used after work already started?
- Should recovery draft title stay fixed, or should it derive a lightweight hint from changed files?
- Should multiple active goals remain legal, or should this feature push the repo toward one-active-goal-by-default semantics?

## Suggested Implementation Plan

1. Add internal worktree-detection helpers and a small typed result model.
2. Add active-goal lookup and multiple-active-goal validation.
3. Implement `ensure-active-task`.
4. Integrate strict guard checks into relevant mutating command handlers.
5. Add warning support to `show`.
6. Add regression tests and smoke validation.
7. Update README/help text only after the workflow is proven locally.
