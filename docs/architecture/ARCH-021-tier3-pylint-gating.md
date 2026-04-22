# ARCH-021: Tier 3 pylint code-quality gates

**Status:** done
**Priority:** medium
**Complexity:** low-medium

## Rationale

ARCH-019 enabled Tier 1 (correctness / file-size) and ARCH-020 promoted
Tier 2 (complexity) to hard-fail. A large number of default pylint rules
remained outside any tier — some real-signal (reimported, subprocess-run
without `check=`, unnecessary comprehensions), some noisy style policy
(line-too-long, missing docstrings), some semantically wrong on our code
(too-few-public-methods on `@dataclass`, too-many-return-statements on
dispatch tables).

ARCH-021 curates the remaining rules into a Tier 3 set that adds real
signal without creating style-policy churn, and promotes it to hard-fail
alongside Tier 1 and Tier 2.

## Rules included in Tier 3

| Rule | What it catches |
|------|----------------|
| `W0404` reimported | `import X` twice in the same module |
| `W0621` redefined-outer-name | inner-scope shadowing of a module-level name |
| `W1510` subprocess-run-check | `subprocess.run(...)` without `check=True/False` |
| `R1721` unnecessary-comprehension | `[x for x in seq]` instead of `list(seq)` |
| `R0916` too-many-boolean-expressions | >5 boolean operators in one `if` |
| `C0325` superfluous-parens | parens after `not`/`return`/etc. |
| `R0917` too-many-positional-arguments | public-ish signatures with >5 positional args (force `*,` kwonly) |
| `C0415` import-outside-toplevel | lazy imports — must be justified |
| `W0613` unused-argument | dead-weight parameters (unless interface-conformance) |
| `C0301` line-too-long | at `max-line-length=250` — catches only genuinely huge lines |

## Rules deliberately excluded

| Rule | Reason |
|------|--------|
| `C0114` missing-module-docstring | every module would need a 1-liner; low ROI |
| `C0115` missing-class-docstring | fires on every small `@dataclass` |
| `C0116` missing-function-docstring | 284 findings — docstring-per-private-helper is busywork |
| `R0801` duplicate-code | most findings are legitimately similar SQL/insert blocks |
| `R0903` too-few-public-methods | fires on every `@dataclass` / Protocol |
| `W0212` protected-access | required for `argparse._choices_actions` mutation |
| `R0911` too-many-return-statements | fires on the intentional `cli.main` dispatch chain |
| `R0904` too-many-public-methods | singular outlier (`CommandRuntime` Protocol) |

## Implementation

### Real fixes

- `file_immutability.py`: added `check=False` to the cleanup `subprocess.run`
  so the gate is explicit.
- `usage/resolution.py`: rewrote two `if not (a <= x <= b):` guards into
  positive `if x < a or x > b:` form (removes `C0325` and improves
  readability).
- `commands.py`: replaced `[tuple(row) for row in token_rows]` with
  `list(token_rows)`; lifted the `import json as _json` / `import sys`
  shadows inside `handle_ingest_codex_history` and `handle_history_update`
  to module-top imports.
- `domain/aggregation.py`: extracted `_needs_goal_window_nudge` helper from
  `finalize_goal_update`, removing the 6-boolean `if` chain.
- `usage/backends.py`: inline-disabled `W0613` on `UnknownUsageBackend.resolve_window`
  (interface conformance — all kwargs are intentionally unused) and
  `ClaudeUsageBackend.resolve_window` (protocol requires `logs_path` and
  `thread_id` but Claude JSONL telemetry ignores them).

### Kwonly conversion

Twenty-one functions previously took >5 positional arguments. Each now
uses `*,` to force callers to pass kwargs, matching how they are already
called:

- `resolve_usage_costs` (cli + runtime_facade), `upsert_task`,
  `sync_usage`, `sync_codex_usage` — CLI-surface mutators where kwargs are
  already the convention.
- `resolve_cost_audit_usage_window` (nested closures in cli + runtime_facade).
- `resolve_codex_usage_window`, `_resolve_usage_window_impl` — usage
  resolvers called as part of the `UsageResolver` protocol.
- `_insert_normalized_*` helpers in `history/normalize.py` and
  `_insert_message_facts` / `_insert_goal_and_retry_chain` /
  `_insert_message_fact_row` in `history/derive_insert.py`.
- `_apply_int_token_update` in `domain/aggregation.py`.
- `aggregate_report_data` in `report/aggregation.py` (kwonly for the
  warehouse-series tail).

`UsageResolver` was upgraded from a plain `Callable[...]` alias to a
`Protocol` with kwonly `__call__` so mypy tracks the keyword-only contract
through `CostAuditContext`.

### Top-level import lifts

Lazy imports were hoisted where circular risk is absent (confirmed against
`lint-imports` contracts):

- `cost_audit.py`, `history/compare.py`, `history/audit.py` → `import json` at top.
- `commands.py` → `from datetime import datetime, timezone` and
  `from ai_agents_metrics.report.html_report import aggregate_report_data, check_warehouse_state, render_html_report` at top.
- `cli.py` → `import os`, `ensure_parent_dir`, and
  `audit_cost_coverage as _run_audit_cost_coverage` added to existing
  top-level imports.
- `event_store.py` → `from ai_agents_metrics.domain.time_utils import now_utc_iso` at top.
- `runtime_facade.py` → `ensure_parent_dir` added to the existing storage
  import, `audit_cost_coverage as _run_audit_cost_coverage` added to the
  existing cost_audit import.

### Inline disables with rationale

Four imports stay lazy by design; each now carries a
`# pylint: disable=import-outside-toplevel` with a comment explaining why:

- `__init__.py` — `_version.version` is inside a `try/except ImportError`
  because setuptools_scm generates the file on demand.
- `domain/aggregation.py` — `event_store.replay_events` inside
  `load_metrics` is lazy by import-linter contract (domain layer cannot
  import infrastructure at module top).
- `cli.py` (`merge_tasks` and `main`) — lazy imports of `runtime_facade`
  and `commands` preserve the re-export-shim contract for
  `scripts/metrics_cli.py`, which hoists every non-private `cli.*` name
  into its own module namespace. Hoisting these would drag the entire
  orchestration dependency graph into every CLI import.

### Gate wiring

- `Makefile pylint-check` now runs a third tier stage with the Tier 3 rule
  set and `--max-line-length=250`.
- `pyproject.toml [tool.pylint."messages control"]` includes the Tier 3
  rule codes in its `enable` list and gains a `[tool.pylint.format]`
  section pinning `max-line-length = 250`.

## Acceptance Criteria

- [x] Tier 3 rules run against all modules with zero findings.
- [x] `make verify` fails on any new Tier 3 violation.
- [x] `C0301` uses `max-line-length=250` in both Makefile and pyproject.
- [x] Remaining lazy imports are justified by a contract-level reason
      (circular avoidance, import-linter rule, setuptools_scm).
- [x] `UsageResolver` is a `Protocol` so kwonly conformance is typed.
- [x] Import-linter contracts stay at 6 kept / 0 broken.
