# AI Instructions For A New Python Project

Use this file as an operating brief for an AI engineer starting a new Python project.

The goal is not to maximize cleverness.

The goal is to make development faster by reducing:

- wrong turns
- hidden regressions
- brittle workflows
- manual cleanup
- misleading “success”

## Priority Order

Optimize in this order:

1. requested outcome fidelity
2. fast feedback loops
3. safe iteration
4. maintainability
5. polish

Do not trade outcome fidelity for speed theater.

## Core Working Style

- First understand what works now, not what should work in theory.
- Treat assumptions as risks until verified.
- Prefer diagnosis -> guardrail -> verification over clever but weakly defended fixes.
- Prefer small, reviewable, reversible changes over broad rewrites.
- Preserve a working path until the replacement is proven.
- Treat “adjacent but not requested” output as a primary quality failure.
- Before optimizing, identify the current bottleneck and do not polish a non-constraint.

## Start Every Task Correctly

Before implementing:

- restate the requested outcome
- identify constraints and acceptance criteria
- separate verified facts from guesses
- pick the smallest high-leverage next step

If product framing or success criteria are unclear:

- treat drafts as hypotheses
- do not present guessed framing as settled truth

## Project Setup Defaults

For a new Python project, prefer this baseline:

- `src/` layout
- `pyproject.toml` as the primary config file
- `pytest` for tests
- `coverage.py` or `pytest-cov` for coverage measurement
- `ruff` for linting
- `mypy` for type checking
- `Makefile` or one canonical verify command

Create one standard local validation entrypoint early, such as:

```bash
make verify
```

It should run, at minimum:

- lint
- typecheck
- tests
- coverage

Create coverage reporting at project start, not later.

Minimum expectation:

- coverage is collected from the first meaningful tests
- coverage is part of the standard local verify workflow
- uncovered critical paths are visible early
- integration or subprocess-heavy flows have an explicit coverage strategy instead of being ignored

Do not postpone coverage until “after the project stabilizes”.

Treat the canonical verify command as part of the product contract for the repository.

Do not let validation devolve into a grab-bag of ad hoc commands that different contributors remember differently.

## Architecture Standard

Prefer designs that stay legible under change.

Use these principles actively, not decoratively:

- `SOLID`
- `DDD`
- `GRASP`
- clear separation of orchestration, domain logic, infrastructure, and presentation

Practical interpretation:

- keep domain rules in domain code, not buried in CLI glue
- keep side effects at boundaries
- keep high-level modules depending on explicit contracts, not incidental implementation details
- give objects and modules one clear reason to change where practical
- model important concepts with names the product/user would recognize
- avoid “manager”, “utils”, and “helpers” blobs that collect unrelated decisions

## Anti-Copy-Paste Rule

Actively resist copy-paste architecture.

Do not duplicate logic across:

- command handlers
- validators
- serializers
- report builders
- tests

When duplication appears, decide deliberately:

- if it is harmless presentation duplication, keep it simple
- if it duplicates domain rules or mutation logic, extract a shared boundary or helper

Avoid both extremes:

- copy-paste drift
- premature abstractions that hide simple code

The target is shared truth without unnecessary indirection.

## Code Structure

- Keep domain logic separate from CLI, storage, and reporting concerns.
- Separate these layers early:
  - domain
  - orchestration or commands
  - storage
  - reporting
  - CLI or entrypoints
- Use explicit typed boundaries for important records and mutation flows.
- Prefer dataclasses, typed objects, or schemas over shapeless dictionaries at domain boundaries.
- Preserve compatibility surfaces during refactors until a breaking change is intentional and verified.
- Avoid turning one orchestration file into a god-module.
- Treat shims, public CLI commands, packaged entrypoints, and bootstrap flows as compatibility contracts once users or automation depend on them.

## Testing Strategy

Default to test-first development.

If full TDD is impractical for a task, stay as close to it as possible and still write the test in the same implementation cycle.

The default expectation is:

- write the failing test first
- implement the smallest change that makes it pass
- refactor only while the safety net stays green

For any meaningful behavior change:

- add or update tests in the same task
- do not treat manual testing as an acceptable replacement when automation is practical

For mutating workflows, cover three test buckets when practical:

1. happy path
2. invalid-state rejection
3. output or report consistency after mutation

Use multiple layers of checks:

- unit tests
- regression tests
- CLI/integration tests
- live or smoke checks where real integrations matter

Treat coverage as a diagnostic tool, not a vanity number.

Good coverage usage:

- identify dangerous blind spots
- prove new critical paths are exercised
- make subprocess, packaging, and runtime paths visible

Bad coverage usage:

- chasing percentage without risk reduction
- ignoring hard-to-measure runtime paths
- counting only easy in-process code

Do not assume synthetic tests are enough for real integration boundaries.

When an integration depends on real external or local runtime artifacts, add an opt-in smoke check.

For packaging, bootstrap, or installer flows:

- test the real packaged or installed entrypoint
- not only local source-tree execution

## Validation Rules

- Fail loudly on invalid state.
- Add strict validation early.
- Encode repeated failure modes as tests, types, validation rules, or guardrails.
- Do not leave important integrity rules as informal convention only.
- Validate before mutation when a workflow can partially write or scaffold files.

Examples of high-value validation:

- timestamp ordering
- required status/failure combinations
- acyclic references
- non-negative counters and costs
- stage or lifecycle consistency
- safe rerun behavior
- partial existing state handling
- conflict detection before writes

## Workflow And Task Boundaries

- Keep one requested outcome as one coherent task or goal.
- Do not split work into many tiny “successes” just to make metrics look good.
- Keep retry history visible.
- If the workflow uses staged handoffs, make the current stage explicit.
- Do not silently jump from requirements to implementation to acceptance without a clear handoff.

For product or delivery work:

- record boundaries close to the real work window
- avoid post-hoc zero-duration closeouts
- keep timing and cost windows honest enough for later analysis

Do not automate a workflow that is not yet manually understood end to end.

First prove the manual flow.
Then automate only the parts that are stable and clearly helpful.

## Metrics And Observability

If the project tracks execution metrics:

- track requested outcomes separately from retry history
- do not let top-line success hide failed attempts
- prefer explicit coverage and covered-subset averages over brittle all-or-nothing KPIs
- add diagnostic audit views before adding more summary polish

When a metric looks wrong or incomplete, prefer audit-first diagnosis:

- add a diagnostic command, report, or debug lens
- identify the dominant reason bucket
- only then change the summary metric or workflow

If the system says data is missing, verify whether:

- the source data is actually absent
- the extractor is outdated
- the workflow recorded the wrong boundaries

Absence of recovered data is not the same as absence of source data.

## Handling Retrospectives

Retros are useful only if they feed changes back into the system.

When something painful happens:

1. capture the retrospective
2. identify root cause
3. classify the fix:
   - code change
   - test
   - validation rule
   - local workflow rule
   - documentation only
   - no action

Do not promote every lesson into broad policy.

Prefer the narrowest correct scope.

Good retrospective follow-up targets:

- code change
- test
- validation rule
- local agent rule
- reusable policy only when genuinely portable

## Release And Automation Principles

- Keep a single source of truth for config and important paths.
- Prefer transparent, reproducible scripts over opaque magic.
- Validate the real artifact that users run, not only the source tree.
- Design bootstrap or initializer flows to support safe reruns and partial existing states.
- Separate preflight checks from writes where possible.
- Treat bootstrap, scaffolding, installer, and migration flows as first-class product surfaces.

## Things To Avoid

- rewriting large working areas without proving the need
- polishing KPIs before diagnosing the bottleneck
- inventing product framing without user confirmation
- manual testing when automated testing is practical
- documentation-only “fixes” for repeated engineering failures
- broad abstractions added before repeated concrete pain exists

## Good Operating Loop

Use this loop repeatedly:

1. clarify the outcome
2. inspect current behavior
3. diagnose the bottleneck
4. make the smallest useful change
5. add or strengthen guardrails
6. verify strongly
7. capture the lesson if it is likely to repeat

If a fix changes an integration boundary, add:

8. a targeted diagnostic or smoke check that proves the boundary works in reality

## What “Done” Means

A task is not done when code exists.

A task is done when:

- the requested outcome is actually delivered
- relevant automated verification is green
- important risks are either removed or explicitly stated
- the workflow, metrics, and reporting are consistent with the new behavior

If there is a gap, say so explicitly instead of presenting partial completion as success.
