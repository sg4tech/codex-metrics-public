# Architecture Tasks

Technical debt and structural improvements not tied to specific product features.

Each file is a standalone task. Track via an in-repo metrics goal
(`./tools/ai-agents-metrics start-task --title '...' --task-type meta`) and
commit via `NO-TASK: ARCH-NNN <summary>`. Tickets without an individual
spec file (post-ARCH-023) are documented through their commit messages and
the campaign-level retros in `docs/private/retros/`.

## Tasks

| ID | Title | Priority | Complexity | Status |
|----|-------|----------|------------|--------|
| [ARCH-001](ARCH-001-cli-re-exports.md) | Remove re-exports from cli.py | high | low | closed |
| [ARCH-002](ARCH-002-domain-split.md) | Split domain.py into layers | high | medium | done |
| [ARCH-003](ARCH-003-timestamps-as-datetime.md) | Store timestamps as datetime in dataclasses | medium | medium | done |
| [ARCH-004](ARCH-004-save-metrics-hidden-pop.md) | Remove hidden transformation from save_metrics | medium | low | obsolete |
| [ARCH-005](ARCH-005-detect-started-work-location.md) | Move detect_started_work out of cli.py | medium | low | done |
| [ARCH-006](ARCH-006-pipeline-typed-contracts.md) | Add typed contracts between pipeline stages | medium | medium | done |
| [ARCH-007](ARCH-007-legacy-supersedes-map.md) | Remove LEGACY_GOAL_SUPERSEDES_MAP from domain.py | low | low | done |
| [ARCH-008](ARCH-008-cli-command-reference.md) | Write CLI command reference | medium | low | done |
| [ARCH-009](ARCH-009-subprocess-coverage.md) | Automate subprocess coverage without manual env toggle | low | low | open |
| [ARCH-010](ARCH-010-bandit-security-scan.md) | Integrate bandit security scanner into verify | medium | low | done |
| [ARCH-011](ARCH-011-radon-metrics.md) | Integrate radon for code complexity metrics | medium | low | done |
| [ARCH-012](ARCH-012-import-linter.md) | Integrate import-linter for architectural boundary enforcement | medium | low | done |
| [ARCH-013](ARCH-013-decompose-high-complexity-functions.md) | Decompose high-complexity orchestrator functions (derive_codex_history, aggregate_report_data) | high | high | done |
| [ARCH-014](ARCH-014-extract-usage-resolution-from-cli.md) | Extract usage resolution functions out of cli.py (eliminate lazy circular imports) | medium | medium | done |
| [ARCH-015](ARCH-015-sqlalchemy-migration.md) | Migrate from raw sqlite3 to SQLAlchemy Core | medium | high | planned |
| [ARCH-016](ARCH-016-propagate-model-to-derived-tables.md) | Propagate model to all derived tables | medium | low | done |
| [ARCH-017](ARCH-017-html-report-dimensions.md) | Add provider and model dimensions to HTML report | high | medium | done |
| [ARCH-018](ARCH-018-layer-separation-cleanup.md) | Honor layer separation — move interpretation out of raw_* tables | medium | medium | open |
| [ARCH-019](ARCH-019-global-pylint-rollout.md) | Globally enable pylint across the whole project | medium | medium | done |
| [ARCH-020](ARCH-020-tier2-pylint-gating.md) | Promote Tier 2 pylint complexity rules to hard-fail | medium | medium | done |
| [ARCH-021](ARCH-021-tier3-pylint-gating.md) | Promote Tier 3 pylint code-quality rules to hard-fail | medium | low-medium | done |
| [ARCH-022](ARCH-022-tier3-pylint-followup.md) | Tier 3 follow-up — R0904/W0212/R0801 gating + explicit R0903/R0911 skip | medium | medium | done |
| [ARCH-023](ARCH-023-pylint-single-run.md) | Collapse Tier 1/2/3 into a single default pylint run | low | low | done |
| ARCH-024 | Replace low-hanging pylint disables with real refactors (C + B + A) | medium | low-medium | done |
| ARCH-025 | Enforce C0114 module docstrings; prune zero-finding disables | low | low | done |
| ARCH-026 | Expand ruff from 2 to 15 rule categories | medium | low | done |
| ARCH-027 | Split `commands.py` (1340 lines) into `commands/` package | medium | medium | done |
| ARCH-028 | Split `runtime_facade.py` (927 lines) into `runtime_facade/` package | medium | medium | done |
| ARCH-029 | Gate mypy strict on `domain/` + `history/`; add hypothesis property tests (16 invariants) | medium | medium | done |
| ARCH-030 | Enable `mypy --strict` globally at `[tool.mypy]` | low | low | done |
| ARCH-031 | Remove stale `too-many-lines` disable from `aggregation.py` | trivial | trivial | done |
| ARCH-032 | Drop 11 inline suppressions via real refactors (SIM118 + re-exports) | low | medium | done |
| ARCH-033 | Bundle `upsert_task` kwargs into dataclass to drop `too-many-arguments` disables | medium | high | **aborted** |
| ARCH-034 | Split `history/ingest.py` (1152) + `cli.py` (1091) into packages | medium | medium | done |

## Recommended order

1. ~~**ARCH-001**~~ ✓ ~~**ARCH-005**~~ ✓
2. ~~**ARCH-004**~~ (obsolete) and ~~**ARCH-008**~~ ✓ — isolated, done independently
3. ~~**ARCH-002**~~ ✓ — domain/ package complete
4. ~~**ARCH-003**~~ ✓ — timestamps are `datetime` in all dataclasses
5. ~~**ARCH-007**~~ ✓ — isolated, constant removed
6. ~~**ARCH-006**~~ ✓ — typed contracts at normalize→derive boundary
7. **ARCH-009** — low priority; improves dev tooling (subprocess coverage automation)
8. **ARCH-010** — medium priority; enforces security scanning in CI/CD (fix B110 exception handling + B608 SQL patterns)
9. **ARCH-011** — medium priority; identifies overly complex functions and modules needing decomposition (radon metrics)
10. **ARCH-012** — medium priority; enforces architectural layer boundaries as code grows (import-linter rules)
11. **ARCH-013** — high priority; `derive_codex_history` (CC=85) and `aggregate_report_data` (CC=70) are untestable monoliths; decompose before further growth
12. **ARCH-014** — medium priority; lazy `cli` imports in `usage/backends` and `commands` are a circular dep workaround; unblock import-linter contract after fix
13. **ARCH-015** — medium priority; replace raw sqlite3 SQL strings with SQLAlchemy Core for safer, composable queries as complexity grows
14. **ARCH-016** — medium priority; model is in `normalized_usage_events` but missing from `derived_session_usage`, `derived_attempts`, and always NULL in `derived_goals`; prerequisite for H-039 warehouse export
15. **ARCH-017** — high priority; HTML report has no provider/model breakdown — the most actionable cost dimensions are invisible; Phase 1 (total cost, Chart 3 fallback, UX polish) has no deps; Phase 2 (model breakdown) depends on ARCH-016
16. **ARCH-018** — medium priority; `raw_messages` / `raw_token_usage` / `raw_session_events` parse source payload into typed fields, violating the Layer 1 byte-perfect rule defined in `warehouse-layering.md`; replace with `raw_events` + unparsed payload, move typing to existing `normalized_*` tables
17. **ARCH-019** — medium priority; `pylint` exists but still excludes major modules and only enforces a selective subset of rules; define and execute a staged rollout to make full-project `pylint` practical
18. **ARCH-020** — medium priority; Tier 2 complexity rules were advisory after ARCH-019; promote them to hard-fail so `make verify` blocks complexity regression (64 starting findings resolved via params dataclasses, decomposition, and scoped inline disables on canonical data schemas and CLI-contract boundaries)
19. **ARCH-021** — medium priority; curate the remaining default pylint rules into a Tier 3 set that catches real code-quality issues (reimported, subprocess-run-check, unnecessary-comprehension, kwonly conversion, lazy-import justification) while deliberately skipping style-policy noise (docstring-per-helper, line-too-long at 100); promoted to hard-fail alongside Tier 1 and Tier 2
20. **ARCH-022** — medium priority; re-review the five rules parked by ARCH-021. Promote R0904/W0212/R0801 to hard-fail (eliminate cli ↔ runtime_facade duplication at source, narrow-scope inline disables for argparse private API and `CommandRuntime` Protocol breadth). Explicitly keep R0903/R0911 excluded (false positives on `@dataclass` and `cli.main` dispatch).
21. **ARCH-023** — low priority; once all tiers are hard-fail, the tier framing is just cost. Collapse the three pylint invocations in `make verify` into a single default run; replace the `disable = "all"` / `enable = [...]` whitelist in pyproject with a reasoned `disable = [...]` blacklist so rule changes happen in one place.

## Post-ARCH-023 cleanup campaign (2026-04-22)

Tickets ARCH-024 through ARCH-034 were landed as a single one-session campaign
that followed naturally from the pylint work — once all rules were live, removing
stale suppressions and splitting oversized files became the obvious next step.
These entries live in the table above without individual spec files (the commit
messages and the campaign retro carry the full reasoning).

- **ARCH-024/025/026** — incremental lint cleanup (real refactors, module
  docstrings, wider ruff ruleset).
- **ARCH-027/028/034** — split the four files that were ≥900 lines
  (`commands.py`, `runtime_facade.py`, `history/ingest.py`, `cli.py`) into
  cohesive packages. Result: zero src files ≥900 lines.
- **ARCH-029/030** — mypy strict gating. ARCH-029 used a per-module override
  for `domain/` + `history/` (workaround for a mypy 1.20 bug with
  `strict = true` in overrides). ARCH-030 promoted strict to the top-level
  `[tool.mypy]` block once a one-line fix in `usage/backends.py:135`
  unblocked the rollout. Also adds hypothesis property tests: 16 invariants
  split evenly between `domain/aggregation.py::recompute_summary` and
  `history/normalize.py::normalize_codex_history`.
- **ARCH-031/032** — inline suppression cleanup: 55 → 43 real suppressions
  via stale-removal + SIM118 try/except + test migration off `importlib` reflection.
- **ARCH-033** (aborted) — proposed dataclass bundling for
  `resolve_goal_usage_updates` / `upsert_task` to drop `too-many-arguments`.
  Aborted before coding: ~300-line refactor across 6 files with a public
  runtime_facade signature break, for 3 comment-line removals. The remaining
  suppressions are documented as deliberate ("Wide kwargs surface reflects
  the CLI update contract; grouping tracked once precedence rules stabilise").

Public commits for every ticket are reachable via `git log --grep="ARCH-02[4-9]\|ARCH-03[0-4]"`.
