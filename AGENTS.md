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
- Treat assumptions as risks until verified.

## Metrics tooling

Do not edit metrics files manually when the updater script can regenerate them.

Use:

`python scripts/update_codex_metrics.py ...`

Generated files:
- `metrics/codex_metrics.json`
- `docs/codex-metrics.md`

## Metrics workflow

For every engineering task involving the metrics system:

1. create or continue a goal record
2. set or confirm the goal type:
   - `product` for product or engineering delivery
   - `retro` for retrospective analysis and retro writeups
   - `meta` for bookkeeping, audits, process/tooling governance, and non-product support work
   - for new goals, always pass the goal type explicitly
   - if a new goal intentionally continues or supersedes a prior closed goal, link it explicitly with `--continuation-of` or `--supersedes-task-id`
3. update attempts on each new implementation pass for the same goal
4. update cost or tokens when available
5. close the goal as `success` or `fail`
6. regenerate:
   - `metrics/codex_metrics.json`
   - `docs/codex-metrics.md`

Metrics bookkeeping is part of the definition of done.

Retrospectives must not be mixed into product-delivery goal metrics without classification.
Reports should make retrospective work and product-development work distinguishable.
Source of truth should use `goals + entries`, with summary reported by effective goal chains rather than raw linked records.
Entries should represent attempt history, not a mirrored copy of goal records.
When reporting current project health, do not present goal-level success alone if entry-level failures exist; surface both the effective goal view and the raw entry view so retry pressure stays visible.
Inferred attempt-history entries may be used to preserve history shape, but they must not pollute diagnostic failure-reason reporting.

## Script editing rules

When editing `scripts/update_codex_metrics.py`:

- preserve CLI behavior unless explicitly asked otherwise
- prefer additive changes over breaking changes
- keep the code simple and readable
- add or update tests together with behavior changes
- do not manually patch generated outputs when the script can regenerate them
- validate inputs strictly
- fail loudly on invalid state instead of silently continuing

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

When running `init` or any destructive regeneration smoke check during validation, prefer temporary metrics/report paths instead of real repository artifacts unless the task explicitly requires regenerating the tracked files.
Generated metrics files are production-like artifacts for this repository and must not be casually overwritten during smoke testing.
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
- `AGENTS.md` stores project rules; `docs/retros/` stores incident history and lessons.
- After a meaningful task is completed successfully and the retrospective is logged, create a git commit for the finished checkpoint.
- Do not create a commit just because lint passed or only a partial technical check succeeded; commit only after the actual task outcome is complete and stabilized.
