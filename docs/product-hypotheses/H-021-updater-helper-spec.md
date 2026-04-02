# Feature Spec: Privileged Updater Helper For An Immutable Metrics File

## Status

- Draft date: `2026-04-03`
- Owner: `product / metrics`
- Intended audience: `development team`
- Related hypothesis: [H-021](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-021.md)

## Problem

The structured metrics file is the source of truth, so accidental edits are expensive. A system-level immutable flag can reduce accidental mutation, but it also blocks the normal update path.

That means the real design question is not whether the file can be made read-only. The real question is how the repository can keep exactly one narrow, auditable write path that is allowed to temporarily lift the protection, update the file, and restore the protection.

## Goal

Design a safe updater flow for `metrics/codex_metrics.json` that assumes the file is immutable by default and is only writable through a constrained privileged helper.

The first version should support at least:

- read-only access for normal users and ordinary scripts
- an explicit privileged update helper
- temporary unlock, write, and re-lock behavior
- a failure mode that leaves the file protected if the update fails partway through

## Non-Goals

This feature should not:

- make the metrics file generally writable again
- rely on manual ad hoc edits
- require provider-specific public commands
- silently downgrade security to make the update easier
- assume the same primitive exists identically on every OS

## Product Intent

The product should make the source-of-truth metrics file harder to corrupt without making it impossible for the canonical updater to do its job.

The public contract remains the same:

- the system should still expose one universal metrics workflow
- the write path should be an internal implementation detail

## Scope

In scope for the first implementation:

- define the privileged helper as the only sanctioned writer
- use OS-level immutability as the default protection
- temporarily remove the immutable bit only inside the helper
- write the regenerated metrics file
- re-apply immutability before exit
- add tests or smoke checks around the helper contract

Out of scope for the first implementation:

- full cross-platform packaging
- daemon processes
- remote update services
- broad sudo access
- any design that depends on a human manually toggling permissions

## Proposed Model

### macOS / BSD-style flow

Use `chflags uchg` as the default protection on the metrics file.

The helper path should:

1. clear the user immutable flag
2. regenerate or write the metrics file
3. restore the immutable flag

If the helper cannot restore the lock, it should fail loudly and leave the system in a visibly unsafe state so the problem is obvious.

### Linux flow

Use `chattr +i` as the default protection on the metrics file.

The helper path should mirror the same unlock-write-relock sequence with the Linux primitive.

### Privilege Boundary

The helper should be the only component allowed to run with the privileges needed to clear and restore the immutable flag.

That can be implemented as one of:

- a root-owned helper binary or script
- a tightly scoped `sudoers` rule for exactly one command path
- a small launcher that invokes the real updater under a privileged wrapper

The helper should not be a general shell escape hatch.

## Functional Requirements

### 1. Read-only default

Normal repository work should treat the metrics file as read-only.

### 2. Narrow write path

There must be exactly one sanctioned updater flow that can modify the file.

### 3. Safety on failure

If the update fails after protection is cleared, the helper must either:

- restore protection before exiting, or
- fail in a way that is immediately obvious and recoverable

### 4. Auditability

The privileged path should be easy to identify in logs, scripts, or command history.

## Suggested Analysis Strategy

### Stage 1: Proof of primitive

Verify that the local OS primitive actually blocks normal writes and can be restored cleanly.

### Stage 2: Narrow helper

Define the smallest possible helper that can toggle protection and call the existing metrics writer.

### Stage 3: Failure handling

Add guardrails so the helper does not leave the file unlocked after a crash, interrupt, or partial failure.

## Acceptance Criteria

- the metrics file is protected by default
- normal writes fail
- the sanctioned helper can update the file
- the helper restores protection after a successful update
- the helper leaves the system in a visibly unsafe state only if it fails before re-locking, and that condition is detectable
- the design does not depend on a vague “only the script can write” assumption

## Risks

- the privileged path could become operationally annoying
- unlock/re-lock sequencing could be brittle if the helper is too complex
- cross-platform parity may be harder than expected
- a file-immutability design may still be insufficient if the real threat is privileged misuse rather than accidental drift

## Guardrails

- keep the privileged command path explicit and narrow
- prefer one helper over multiple overlapping write paths
- avoid embedding generic shell evaluation in the privilege boundary
- prefer failing closed over silently leaving the file writable

## Open Questions For Implementation

- should the helper live inside the repository or outside it
- should the privileged path be root-owned helper code or a `sudoers`-restricted command
- do we need a single abstraction that maps to `chflags` on BSD/macOS and `chattr` on Linux
- should the metrics writer be refactored so the helper only wraps the final write call

## Suggested Implementation Plan

1. Prove the local OS immutable primitive on this machine.
2. Define the helper contract and command path.
3. Wrap the existing metrics writer with unlock-write-relock behavior.
4. Add tests or a smoke check for normal write failure and privileged write success.
5. Decide whether the design is worth carrying forward before broadening it.
