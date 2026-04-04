# Linear Task Lifecycle

This is the working Linear task lifecycle for Codex-assisted engineering in this repository.

Use it as the practical operating model for moving a task from planned work to implementation, review, and completion.

The exact Linear team and status names are defined in `docs/local-linear-setup.md`.

## Roles

### Lead

The lead owns task orchestration:

- choose the right task
- decide whether new work belongs in an existing issue or a new one
- move the Linear issue between stages
- decide when a stage is complete
- decide when the work is ready to close

The lead may be a human or an operator acting in that role, but the responsibility stays explicit.

### Implementer

The implementer owns execution inside the current stage:

- write code and tests when the task is in the configured in-progress stage
- keep changes aligned to the requested outcome
- avoid expanding the task into adjacent work without a handoff
- report blockers and uncertainty clearly

### Reviewer / QA

The reviewer owns verification:

- inspect the change for defects, regressions, and missing coverage
- leave concrete follow-up comments when something needs to return to implementation
- accept the work only when the change is actually ready

The same person can fill multiple roles, but the mode should still be explicit.

## Stage Meaning

### Planned Work

Use the configured backlog stage for work that has been approved but has not started yet.

### Implementation

Use the configured in-progress stage when the task is actively being implemented.

Expected behavior:

- write code
- update or add tests
- keep the task scoped to the agreed outcome
- do not mark the task done before review and validation

### Review

Use the configured review stage when the implementation is ready for review.

Expected behavior:

- review the diff
- leave findings or approval comments
- move the issue back to the implementation stage if changes are needed
- keep the task open until the change is accepted

### Completed

Use the configured done stage only when the task is fully finished.

That means:

- implementation is complete
- review is clean or the remaining comments are explicitly accepted
- relevant checks have passed
- nothing material is left to return to the implementation stage

### Close Criteria

Before moving a task to completion, confirm all of the following:

- the requested outcome matches what was actually built
- the acceptance criteria in the Linear issue are satisfied
- review has either approved the change or explicitly accepted any remaining follow-up
- relevant automated checks have passed
- there is no known blocker that would send the task back to implementation
- the completion handoff is recorded in the issue or repo notes

### Definition of Done (thread closing checklist)

Before closing a conversation thread, work through this checklist. Do not ask the user whether to proceed — if an item is incomplete, complete it automatically.

**If the task involved code:**

- Code review was conducted and all comments are resolved
- QA reviewed the change and critical findings are fixed
- Automated tests exist for the new functionality, covering happy path and relevant edge cases

**In all cases:**

- Retrospective: was one needed? if yes, write and commit it to `docs/retros/` now
- Anything from chat that should be preserved has been saved to files (hypotheses, decisions, policy changes, AGENTS.md rules)
- Commit and push are done — do them now if not yet
- If the task included changes to `AGENTS.md`, `docs/task-lifecycle.md`, `docs/codex-metrics-policy.md`, or any other policy/rules file: verify that those changes are merged into `master`. Run `git log master -- <file>` to confirm. If not merged, flag it to the user before closing — these files are read from master and changes in a feature branch have no effect.

## Transition Rules

The default flow is:

1. planned work -> implementation
2. implementation -> review
3. review -> implementation when review finds issues
4. review -> completed when the work is accepted

Do not silently skip stage boundaries.

If review uncovers a defect, the task goes back to implementation rather than being forced to completion.

## Minimal Automation Contract

This is the smallest set of repo behaviors needed to make the workflow automatic without adding magic.

### Source Of Truth

- The Linear issue status is the stage.
- The status names and team configuration live in `docs/local-linear-setup.md`.
- The current repo task follows that stage.
- The task does not silently change stage without an explicit handoff.

### Required Handshakes

1. Before meaningful work starts, ensure there is an active task.
2. When implementation begins, move the issue to the configured in-progress stage.
3. When the change is ready for review, move the issue to the configured review stage.
4. If review finds problems, move the issue back to the configured in-progress stage and leave concrete findings.
5. If review passes and validation is green, move the issue to the configured done stage.

### Repo Commands That Support The Flow

- `codex-metrics start-task` creates the active task for a new piece of work.
- `codex-metrics continue-task` resumes the current task when implementation continues.
- `codex-metrics finish-task --status success` closes the task when the work is accepted.
- `codex-metrics finish-task --status fail` closes the task when the work should stop instead of continuing.
- `codex-metrics ensure-active-task` recovers or verifies task bookkeeping before work continues.

### Decision Rule

Use one shared transition table for all of the above.

Do not spread stage logic across individual commands.
Do not infer status from vibes.
Do not mark the task complete until review and validation both say the work is finished.

## Working Rules

- Keep one active stage per task.
- Treat stage changes as explicit handoffs, not background state drift.
- Keep the current issue as the source of truth for status.
- Use notes or comments to capture what changed at each handoff.
- Prefer the smallest useful change that satisfies the task.

## Relationship To Other Docs

- `docs/local-linear-setup.md` describes the repo's current Linear team and workflow configuration.
- `docs/pilots/task-lifecycle-fsm-plan.md` captures the implementation shape for the CLI-side lifecycle enforcement work.
- `docs/pilots/task-lifecycle-pilot.md` is historical and should not be treated as the active operating model.
