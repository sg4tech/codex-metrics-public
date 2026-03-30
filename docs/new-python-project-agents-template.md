# AGENTS.md Template For A New Python Project

## Read First

Before starting work, read:

- `AGENTS.md`
- `README.md`
- `pyproject.toml`

If the repository has project-specific policy or architecture docs, read those too before implementing.

## Core Working Style

- First understand what currently works.
- Treat assumptions as risks until verified.
- Prefer diagnosis -> guardrail -> verification over clever but weakly defended fixes.
- Prefer small, reviewable, reversible changes over broad rewrites.
- Preserve a working path until the replacement is proven.
- Treat “adjacent but not requested” output as a primary quality failure.
- Before optimizing anything, identify the current bottleneck and do not polish a non-constraint.

## Delivery Standard

- Default to test-first development.
- For any meaningful behavior change, add or update automated tests in the same task.
- Do not rely on manual testing when automated testing is practical.
- Run the strongest available local verification before calling work complete.
- If the result is partial, say so explicitly instead of presenting it as success.

## Required Tooling

The project should have, from the start:

- `pytest`
- `coverage.py` or `pytest-cov`
- `ruff`
- `mypy`
- one canonical local verify entrypoint, preferably `make verify`

Use strict or near-strict typing by default.

- prefer the strictest practical `mypy` settings
- avoid `Any` unless there is a clear boundary reason
- do not pass raw untyped dictionaries through domain logic when typed records or schemas are practical
- treat typing as a safety tool, not as optional documentation

Coverage is mandatory from the beginning.

- collect it from the first meaningful tests
- keep it in the standard verify workflow
- use it to expose blind spots, not as a vanity number

## Architecture Rules

Use these principles actively:

- `SOLID`
- `DDD`
- `GRASP`

Practical rules:

- keep domain logic separate from CLI, storage, and reporting
- separate domain, orchestration, storage, reporting, and entrypoints early
- keep domain pure; do not make domain logic depend directly on CLI, filesystem, database, HTTP, or transport details
- use an application layer for orchestration; keep business rules in domain logic or domain policies, not in handlers
- keep side effects at boundaries
- use explicit typed boundaries for important records and mutation flows
- prefer dataclasses, typed objects, or schemas over shapeless dictionaries
- keep invariants owned by one aggregate or boundary instead of re-implementing the same rule in multiple layers
- prefer composition over inheritance unless inheritance clearly simplifies the model
- prefer explicit dependencies and constructor injection over hidden globals or implicit shared state
- avoid god-modules and “utils/helpers” dumping grounds
- treat public CLI commands, shims, bootstrap flows, and packaged entrypoints as compatibility contracts once they are used

## Anti-Copy-Paste Rule

- Do not duplicate domain rules across handlers, validators, serializers, or reports.
- If duplication is harmless presentation duplication, keep it simple.
- If duplication repeats domain or mutation logic, extract a shared boundary or helper.
- Avoid both copy-paste drift and premature abstraction.

## Testing Rules

For important mutating flows, cover when practical:

1. happy path
2. invalid-state rejection
3. output or report consistency after mutation

Use multiple test layers as needed:

- unit tests
- regression tests
- integration or CLI tests
- opt-in smoke tests for real integration boundaries

If packaging, bootstrap, or installer behavior matters, test the real packaged or installed entrypoint, not only source-tree execution.

## Validation Rules

- Fail loudly on invalid state.
- Encode repeated failure modes as tests, types, validation rules, or guardrails.
- Validate before mutation when a workflow can partially write or scaffold files.

High-value validation includes:

- timestamp ordering
- required status/failure combinations
- non-negative counters and costs
- acyclic references
- safe rerun behavior
- partial existing state handling
- conflict detection before writes

## Workflow Rules

- Keep one requested outcome as one coherent task or goal.
- Do not split one outcome into many tiny successes.
- Keep retry history visible.
- If using stages, make the current stage explicit.
- Do not silently jump between requirements, analysis, implementation, review, QA, and acceptance.

For delivery work:

- record boundaries close to the real work window
- avoid post-hoc zero-duration closeouts
- keep timing and cost windows honest enough for later analysis

Do not automate a workflow that is not yet manually understood end to end.

## Metrics And Observability

If the project tracks execution metrics:

- separate requested outcomes from retry history
- do not let top-line success hide failed attempts
- prefer explicit coverage and covered-subset averages over brittle all-or-nothing KPIs
- add diagnostic audit views before adding more summary polish

If a metric looks wrong or incomplete, diagnose first:

- check whether source data is actually missing
- check whether the extractor or workflow boundary is wrong
- only then change the metric or workflow

## Retrospective Logging

- Log a retrospective for meaningful bugs, repeated failures, false successes, costly debugging episodes, or process misses.
- Do not write retros for trivial noise.
- Keep retros short and operational.
- Retros should capture at minimum:
  - situation
  - what happened
  - root cause
  - retrospective
  - conclusions
  - permanent changes
- For significant incidents, prefer using `5 Whys` and `Theory of Constraints`.
- Every retrospective must end with a classified follow-up:
  - local `AGENTS.md`
  - reusable external policy
  - tests or code guardrails
  - retrospective only
  - no action
- Prefer the narrowest correct scope.
- Do not promote a lesson into reusable policy unless it is genuinely reusable beyond the local project workflow.
- `AGENTS.md` stores standing project rules; retros store incident history and lessons.

## Retrospective Rules

When something painful happens:

1. capture the retrospective
2. identify root cause
3. classify the follow-up as one of:
   - code change
   - test
   - validation rule
   - local workflow rule
   - documentation only
   - no action

Prefer the narrowest correct scope.

## Definition Of Done

Work is done only when:

- the requested outcome is actually delivered
- relevant automated verification is green
- important risks are removed or explicitly stated
- the resulting behavior is consistent with tests, tooling, and project rules
