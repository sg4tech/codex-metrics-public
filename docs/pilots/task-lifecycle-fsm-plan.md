# Task Lifecycle FSM Plan

## Decision

We should treat task lifecycle handling as an explicit finite state machine instead of a cluster of ad hoc guards inside individual CLI commands.

The trigger for this decision was a false positive in the active-task enforcement path:

- the intended protection was correct
- the boundary was too coarse
- repair-style commands were accidentally treated like active-work continuation

The root problem is therefore not just a missing test. It is a missing state model.

## Why This Is The Right Shape

The current workflow already has distinct modes that behave differently:

- no active goal
- active goal exists
- closed-goal repair
- repository work detected without bookkeeping
- detection uncertain

Trying to encode those modes as scattered `if` checks makes it too easy to over-block or under-block a command.

An FSM gives us:

- one place to define states
- one place to define transitions
- one place to define guard conditions
- one place to prove what is allowed and what is blocked
- a direct way to build complete test coverage by state and event

## Desired Properties

The refactor should satisfy these rules:

- preserve every currently working command path unless a regression is intentionally requested and proven
- active-work continuation and closed-goal repair must remain distinct
- a blocked transition must be explainable from state + event alone
- the workflow should be testable as a matrix of state/event cases
- guard logic should be centralized instead of duplicated across commands
- the public CLI surface should remain agent-agnostic
- we should write the tests first and only then move behavior into the FSM layer

## Non-Negotiable Constraints

These are the guardrails for the refactor:

- do not break behavior that already works today
- keep the public CLI surface stable unless we explicitly approve a breaking change later
- preserve the current repair path for closed goals
- keep `continue-task` strict on active-work enforcement
- add or update tests before changing production behavior
- treat any uncovered transition as incomplete work, not as a minor gap

## Proposed States

Start with a narrow, practical state model:

- `clean_no_active_goal`
- `started_work_without_active_goal`
- `active_goal_exists`
- `closed_goal_repair`
- `detection_uncertain`

These are workflow states, not storage states.
They should reflect the repository + ledger situation the CLI is responding to.

## Proposed Events

The first pass only needs the commands we already rely on:

- `start-task`
- `continue-task`
- `finish-task(success)`
- `finish-task(fail)`
- `update(create)`
- `update(close)`
- `update(repair)`
- `ensure-active-task`
- `show`

## Approval Table

This is the compact state/event view we should use for approval before implementing the FSM.

| State | `start-task` | `continue-task` | `finish-task(success)` | `finish-task(fail)` | `update(create)` | `update(close)` | `update(repair)` | `ensure-active-task` | `show` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `clean_no_active_goal` | allowed, create active goal | blocked if it would continue work | allowed only if explicitly closing a goal record | allowed only if explicitly closing a goal record | allowed | allowed only for repair-style close | allowed only for repair-style close | no-op if no started work | summary only |
| `started_work_without_active_goal` | allowed, create active goal | blocked | allowed as repair | allowed as repair | allowed only if explicit create path | allowed as repair | allowed as repair | create recovery draft | warning only |
| `active_goal_exists` | allowed, create or continue active goal according to existing rules | allowed | allowed | allowed | allowed | allowed | allowed | no duplicate created | summary only |
| `closed_goal_repair` | allowed only if creating a new goal | blocked unless the command is explicitly a repair continuation | allowed | allowed | allowed | allowed | allowed | no-op or blocked depending on detected work | summary only |
| `detection_uncertain` | allowed if the ledger path is valid | allowed with no active-work enforcement because detection is unavailable | allowed if the command is a valid explicit close/repair path | allowed if the command is a valid explicit close/repair path | allowed if the command is a valid explicit create path | allowed if the command is a valid explicit close/repair path | allowed if the command is a valid explicit close/repair path | no-op with explicit uncertainty message | warning only |

## Strict Blueprint

This is the more exact implementation-facing version of the same approval model.

| State | Event | Guard | Decision | Tests To Add |
| --- | --- | --- | --- | --- |
| `clean_no_active_goal` | `start-task` | no active goal and no started work | `allow` | create new active goal; preserve summary validity |
| `clean_no_active_goal` | `continue-task` | no active goal | `block` | confirm blocked exit and message |
| `clean_no_active_goal` | `finish-task(success)` | explicit close of an existing goal only | `allow` | close path without active-work detection regression |
| `clean_no_active_goal` | `finish-task(fail)` | explicit close of an existing goal only | `allow` | failure close path with `failure_reason` validation |
| `clean_no_active_goal` | `update(create)` | new goal creation intent | `allow` | create path still works exactly as today |
| `clean_no_active_goal` | `update(close)` | explicit close intent | `allow` | repair close remains valid in clean repo |
| `clean_no_active_goal` | `update(repair)` | repair intent only | `allow` | repair path can mutate closed goal safely |
| `clean_no_active_goal` | `ensure-active-task` | no started work detected | `no_op` | no duplicate goal; explicit no-op message |
| `started_work_without_active_goal` | `continue-task` | started work detected and no active goal | `block` | blocked path with clear guidance |
| `started_work_without_active_goal` | `finish-task(success)` | repair path allowed even without active goal | `allow` | closed-goal repair in dirty worktree |
| `started_work_without_active_goal` | `finish-task(fail)` | repair path allowed even without active goal | `allow` | failed close in dirty worktree |
| `started_work_without_active_goal` | `update(close)` | explicit close intent | `allow` | repair close in dirty worktree |
| `started_work_without_active_goal` | `update(repair)` | explicit repair intent | `allow` | repair update in dirty worktree |
| `started_work_without_active_goal` | `ensure-active-task` | started work detected | `allow` | recovery draft created exactly once |
| `active_goal_exists` | `continue-task` | active goal exists | `allow` | continue path remains available |
| `active_goal_exists` | `ensure-active-task` | active goal exists | `no_op` | no duplicate recovery draft |
| `active_goal_exists` | `finish-task(success)` | active goal exists | `allow` | close success path unchanged |
| `active_goal_exists` | `finish-task(fail)` | active goal exists | `allow` | close fail path unchanged |
| `closed_goal_repair` | `finish-task(success)` | closed-goal repair intent | `allow` | repair path stays open |
| `closed_goal_repair` | `update(repair)` | closed-goal repair intent | `allow` | repair update stays open |
| `detection_uncertain` | `ensure-active-task` | detection unavailable or untrusted | `no_op` | uncertainty message, no duplicate goal |
| `detection_uncertain` | `continue-task` | detection unavailable or untrusted | `allow` | continue path stays available when detection is unavailable |

## Refactor Plan

### Phase 1: Define the state model

Deliverables:

- a typed workflow-state model
- a single detection function that maps repository + ledger context to a state
- a short decision enum such as `allowed`, `blocked`, `no_op`, `create_recovery_draft`

Exit criteria:

- the current command checks can be expressed as state/event decisions
- the guard boundary is explicit in one place
- the initial test matrix is written before the production refactor lands

### Phase 2: Centralize transition logic

Deliverables:

- a transition table or transition function for the core commands
- explicit handling for repair vs active-work continuation
- command-level wrappers that only orchestrate I/O and persistence

Exit criteria:

- `continue-task` still blocks when it should
- `finish-task` repair paths stay open
- `update` behavior is decided by the event intent, not by a broad mutation bucket
- existing tests still pass before and after the transition layer moves

### Phase 3: Add matrix coverage

Deliverables:

- tests organized by state
- tests organized by event
- negative-path coverage for every command/state combination that should fail
- no-op coverage for safe idempotent paths

Exit criteria:

- every transition in the table has at least one test
- every blocked transition has at least one explicit rejection test
- every repair path has at least one explicit positive test

### Phase 4: Tighten invariants and messages

Deliverables:

- clearer error messages that name the state and the blocked event
- helper output for `ensure-active-task` and `show` that reflects the FSM state
- optional audit/report helpers that reuse the same state model

Exit criteria:

- the same vocabulary appears in CLI behavior, tests, and docs
- the system can explain why a command was blocked

### Phase 5: Simplify the command layer

Deliverables:

- remove duplicated guard logic from individual handlers
- keep command wrappers thin
- leave the FSM as the source of truth for lifecycle decisions

Exit criteria:

- command handlers become orchestration only
- lifecycle policy lives in the FSM layer

## Coverage Standard

The goal is not vague “good coverage”.

The goal is full matrix coverage of the lifecycle rules:

- every state
- every meaningful event
- every allowed transition
- every blocked transition
- every idempotent no-op
- every repair path

That is the protection against repeating the same class of mistake.

## Test Coverage To Add

These are the gaps that need explicit tests before the FSM refactor is considered fully covered:

- `clean_no_active_goal` + `start-task` -> create new active goal
- `clean_no_active_goal` + `ensure-active-task` -> no-op when no started work exists
- `clean_no_active_goal` + `show` -> no warning, summary still prints
- `started_work_without_active_goal` + `ensure-active-task` -> create recovery draft
- `started_work_without_active_goal` + `continue-task` -> blocked with clear message
- `started_work_without_active_goal` + `finish-task(success)` -> allowed as repair
- `started_work_without_active_goal` + `finish-task(fail)` -> allowed as repair
- `started_work_without_active_goal` + `update(close)` -> allowed as repair
- `started_work_without_active_goal` + `update(repair)` -> allowed as repair
- `active_goal_exists` + `continue-task` -> allowed
- `active_goal_exists` + `finish-task(success)` -> allowed
- `active_goal_exists` + `finish-task(fail)` -> allowed
- `active_goal_exists` + `update(create)` -> allowed
- `active_goal_exists` + `ensure-active-task` -> no duplicate created
- `detection_uncertain` + `ensure-active-task` -> no-op with explicit uncertainty message
- `detection_uncertain` + `continue-task` -> blocked or deferred according to the final policy decision
- `closed_goal_repair` + `finish-task` / repair `update` -> allowed
- every blocked path should assert both exit code and explanatory text
- every allowed path should assert both state mutation and ledger validity
- every no-op path should assert that no duplicate goal was created

To reach full coverage, the test suite should also include:

- one explicit test per state for `show`
- one explicit test per state for the active-task detection helper
- one explicit test for each repair-path command in a dirty worktree
- one explicit regression test for every command that shares the update pipeline
- one end-to-end smoke for “state detected -> decision made -> metrics file still valid”

## Approval Checkpoints

Before moving to the next phase, confirm:

1. the state list is complete enough for the first implementation
2. the event list matches real CLI behavior
3. the repair path remains explicitly distinct from active-work continuation
4. the planned test matrix is acceptable

## Open Questions

- Should `show` remain a warning-only path, or should it expose the FSM state more directly?
- Should `update` classification be based on parsed intent flags or on a dedicated command wrapper?
- Should the FSM live in `domain.py`, a new `workflow_state_machine.py`, or a smaller dedicated lifecycle module?

## Notes Captured From Discussion

These points were explicitly agreed in the chat and should be treated as part of the implementation contract:

- preserve every behavior that already works today
- write tests first, then move behavior into the FSM
- prefer a single dispatcher/helper for workflow resolution instead of repeated ad hoc guards
- treat the repair path for closed goals as distinct from active-work continuation
- verify the change with a wider repo-level check before stopping, not just the narrow FSM test set
- do not create a separate retrospective for a successful stabilization step unless a new incident or regression appears

## Recommendation

Start with the narrowest useful FSM:

- keep the existing CLI surface
- move lifecycle decisions into a single state/transition layer
- cover that layer with a matrix of explicit state/event tests

That gives us a real proof surface before any broader refactor.
