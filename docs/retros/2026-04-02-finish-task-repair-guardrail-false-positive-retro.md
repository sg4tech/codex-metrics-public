# Finish-Task Repair Guardrail False Positive Retrospective

## Situation

We added a strong active-task guardrail to prevent continuing real repository work without first recovering or enforcing bookkeeping.

That guardrail solved the intended problem, but it also introduced a false positive:

- `continue-task` on an existing goal should be blocked when work has already started and no active goal exists
- `finish-task` and status-closing `update` should still be allowed as narrow repair paths for closed-goal history correction
- the first implementation treated those cases too similarly

The result was an overly broad validation failure on a command path that was supposed to remain available for history repair.

## What Happened

- The CLI already had repository-local detection for started work.
- The first guard implementation checked whether a task mutation was happening on an existing goal.
- That check was good enough for the active-work continuation path, but not for closed-goal repair.
- When the user tried to close or repair an already-recorded goal after the repository had meaningful changes, the guardrail read the command too broadly and rejected a valid workflow.
- The fix was to split the guard by command intent:
  - keep strict enforcement for `continue-task`
  - allow `finish-task`
  - allow `update` when it is explicitly closing or repairing a goal
- A regression test was added so the repair path stays open while active-work continuation remains blocked.

## Root Cause

The root cause was incomplete negative-path validation.

I did not run the critical scenario that would have exposed the mistake before declaring the fix ready:

- a closed goal
- in a dirty worktree
- with no active `in_progress` goal
- then a repair-style command such as `finish-task` or a closing `update`

Because that scenario was not exercised, I treated the first guard as if it had validated the real boundary between active-work continuation and closed-goal repair.

It had not.

## 5 Whys

1. Why did `finish-task` or `update` fail when they should have been allowed?
   Because the active-task guard treated the command as if it were continuing current work.

2. Why did the guard treat it that way?
   Because the first implementation used a broad “existing-goal mutation” check instead of checking the actual command intent.

3. Why was command intent not part of the guard decision?
   Because we optimized for the quickest strong invariant, not for a fuller state-machine split between active work and history repair.

4. Why is that split important?
   Because active-work continuation and closed-goal repair have different risk profiles and should not be governed by the same enforcement rule.

5. Why did this matter operationally?
   Because when the guard is too broad, operators are pushed toward manual JSON patching or other bypasses, which weakens the source of truth instead of protecting it.

## Theory Of Constraints

The bottleneck was not validation strength in general.

The bottleneck was the decision boundary:

- the system needed to protect live work continuation
- without blocking narrow repair operations on already-closed history

Once that boundary was wrong, stronger validation only amplified the error.

The highest-leverage fix was therefore not “more validation”.
It was “better classification of command intent”.

## Retrospective

This was a useful failure because it exposed a common trap in workflow guardrails:

- a rule can be directionally correct
- and still be too coarse for real operator behavior

The important lesson is to separate:

- actions that extend active work
- actions that repair completed history

Those should share policy language, but not necessarily the same runtime gate.

The repair path is especially important in a metrics system.
If the tool blocks legitimate history correction, users will eventually bypass the tool, which is worse than a narrower and more precise guard.

## Conclusions

- The bug was not in the idea of active-task enforcement.
- The bug was in applying that enforcement too broadly.
- `continue-task` should stay strict.
- `finish-task` and status-closing `update` should remain available as repair paths.
- The best guardrail is one that blocks active-work drift without pushing users back to manual JSON edits.

## Permanent Changes

- Classification:
  - tests or code guardrails
  - local policy clarification
  - retrospective only
- Split the guard logic by command intent instead of treating every existing-goal mutation the same.
- Added a regression test that proves closed-goal repair remains available without an active goal.
- Updated `docs/codex-metrics-policy.md` and the bootstrap policy mirror to clarify that closed-goal repair is allowed, while active-work continuation still prefers `ensure-active-task`.
- Kept the stricter active-work enforcement on `continue-task`.
