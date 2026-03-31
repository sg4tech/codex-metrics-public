# AGENTS.md

## Read first

Before starting or continuing any engineering task, always read:

- `AGENTS.md`
- `docs/codex-metrics-policy.md`

The rules in `docs/codex-metrics-policy.md` are mandatory and are part of this repository's operating instructions.

## Core working style

- First understand what currently works.
- Prefer small, reviewable, reversible changes.
- Do not rewrite working code without a clear reason.
- Preserve backward compatibility unless explicitly asked to change it.
- During module splits or structural refactors, preserve the existing import/export surface until a breaking change is explicitly intended and validated.
- Treat shim modules, entrypoints, and re-exported symbols that are exercised by tests or automation as part of the compatibility contract, not as disposable implementation details.
- Treat assumptions as risks until verified.
- When product framing or success criteria are not yet confirmed by the user, treat drafts as hypotheses, not settled truth.
- Treat “adjacent but not requested” output as a primary quality failure, even if the implementation is otherwise technically strong.
- Prefer diagnosis -> guardrail -> verification over clever but weakly defended fixes.
- Before investing in more metrics semantics, refactoring, or process polish, ask which layer is the current bottleneck; do not optimize a non-constraint.
- For partial-data metrics, prefer explicit coverage and covered-subset averages over brittle all-or-nothing KPIs that collapse to `n/a`.

## Metrics tooling

Do not edit metrics files manually when the updater script can regenerate them.

Use:

`python scripts/update_codex_metrics.py ...`

Generated files:
- `metrics/codex_metrics.json`
- `docs/codex-metrics.md`

For the codex-metrics workflow, goal semantics, reporting invariants, and update/close rules, follow `docs/codex-metrics-policy.md`.
Treat metrics bookkeeping as part of the definition of done for this repository.
Treat metrics from other repositories as read-only inputs for analysis. Never run mutating codex-metrics commands against another project's metrics/report files unless the user explicitly asks for that exact repository to be modified.

## Script editing rules

When editing `scripts/update_codex_metrics.py`:

- preserve CLI behavior unless explicitly asked otherwise
- prefer additive changes over breaking changes
- keep the code simple and readable
- add or update tests together with behavior changes
- for mutating commands such as `update`, `merge-tasks`, and sync flows, cover three test buckets when practical:
  - happy path
  - invalid-state rejection
  - summary/report consistency after mutation
- do not manually patch generated outputs when the script can regenerate them
- validate inputs strictly
- fail loudly on invalid state instead of silently continuing

For repository-initializer or bootstrap-style commands:

- treat them as public-facing initializer flows, not just internal helpers
- design them to support safe reruns and partial existing scaffold states
- separate preflight validation from write execution so conflicts are detected before mutation
- prefer non-destructive failure over partial scaffold writes
- use one canonical wrapped entrypoint for user-facing error handling instead of fixing UX separately per launch surface

For workflow-shaping CLI changes:

- if a new command or command flow is meant to change how agents should work, update `docs/codex-metrics-policy.md` in the same task
- keep the packaged policy mirror in sync with the repo policy
- treat README-only documentation as insufficient for agent-facing workflow changes

## Validation

After changing `scripts/update_codex_metrics.py`:

- run the relevant tests
- run a CLI smoke test
- verify that the script can regenerate both:
  - `metrics/codex_metrics.json`
  - `docs/codex-metrics.md`

Minimum validation commands:

```bash
python -m pytest tests/test_update_codex_metrics.py
python scripts/update_codex_metrics.py init
python scripts/update_codex_metrics.py show
```

Prefer the repository's canonical local validation entrypoint when available:

```bash
make verify
```

After structural refactors, include an entrypoint or compatibility-path check in validation, not just direct module tests.
For bootstrap or initializer commands, do not stop at the empty-repo happy path. Also validate:

- rerun behavior
- partial existing scaffold states
- conflict handling
- `--dry-run` behavior
- the real installed or packaged entrypoint, not only local shims

For packaging or installer changes, treat the local runnable surfaces separately:

- source-tree execution
- `.venv/bin/codex-metrics`
- standalone/global installs when they are part of the user flow

Do not assume refreshing one surface refreshes the others.
When local CLI behavior looks stale, explicitly check `which codex-metrics` and confirm where the package is being imported from before assuming the latest build is in use.

When running `init` or any destructive regeneration smoke check during validation, prefer temporary metrics/report paths instead of real repository artifacts unless the task explicitly requires regenerating the tracked files.
Generated metrics files are production-like artifacts and must not be casually overwritten during smoke testing.
When validating the updater, run dependent commands sequentially, not in parallel.
Examples of dependent flows:
- `update -> show`
- `init -> update`
- any later command that relies on files written by an earlier updater command
Parallel execution is fine only for independent reads and checks such as `ruff`, `mypy`, `pytest`, `rg`, and file inspection.
If `update` output and a parallel `show` disagree, first rerun `show` sequentially before treating it as a product bug.

## Retros Rules

- If the user asks to "сделай ретру" or otherwise requests a retrospective, also log it to a file in `docs/retros/`.
- Each notable incident or debugging episode should be stored as a separate markdown file.
- Retros should capture at minimum:
  - situation
  - what happened
  - root cause
  - retrospective
  - conclusions
  - permanent changes
- For significant incidents, prefer using `5 Whys` and `Theory of Constraints` to separate the symptom from the real bottleneck.
- When a retrospective proposes improvements, classify each proposed change before codifying it:
  - local `AGENTS.md`
  - reusable external policy
  - tests or code guardrails
  - retrospective only
  - no action
- Default retrospective follow-up to the narrowest correct scope.
- Do not promote a lesson into reusable policy unless it is genuinely reusable beyond this repository's local development workflow.
- `AGENTS.md` stores project rules; `docs/retros/` stores incident history and lessons.
- After a meaningful task is completed successfully and the retrospective is logged, create a git commit for the finished checkpoint.
- Do not create a commit just because lint passed or only a partial technical check succeeded; commit only after the actual task outcome is complete and stabilized.

<!-- codex-metrics:start -->
## Codex Metrics

### Read first

Before starting or continuing any engineering task, always read:

- `AGENTS.md`
- `docs/codex-metrics-policy.md`

Use `tools/codex-metrics ...` in this repository.

If `tools/codex-metrics` is unavailable, stop and report an installation or invocation mismatch before proceeding.

The rules in `docs/codex-metrics-policy.md` are mandatory and are part of this repository's operating instructions.

<!-- codex-metrics:end -->
