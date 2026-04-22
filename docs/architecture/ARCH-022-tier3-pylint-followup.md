# ARCH-022: Tier 3 pylint follow-up — R0904/W0212/R0801 + explicit skips

**Status:** done
**Priority:** medium
**Complexity:** medium

## Rationale

ARCH-021 curated the initial Tier 3 pylint rule set and deliberately parked
five defaults (R0801, R0903, R0904, R0911, W0212) pending case-by-case review.
This task reviews each, promotes three to hard-fail (**R0904**, **W0212**,
**R0801**), and explicitly documents the two that stay disabled (**R0903**,
**R0911**) so the intent is clear in future audits.

## Decisions

| Rule | Decision | Reason |
|------|----------|--------|
| **R0801** duplicate-code | **Include** at `min-similarity-lines=40` | Large cli ↔ runtime_facade copies were real duplication; fixed by delegation instead of threshold-bumping. |
| **R0904** too-many-public-methods | **Include** | The only outlier is `CommandRuntime` Protocol (40 methods). Inline-disabled with reason — splitting would fragment the handler type hint without reducing coupling. |
| **W0212** protected-access | **Include** | Two places access argparse internals. `completion.py` narrow module-level disable (stable 3.9–3.13 integration points used by every shell-completion library). `cli.py` narrow block disable around the single `_choices_actions` filter (no public API to hide a subparser after creation). |
| **R0903** too-few-public-methods | **Exclude** | Fires on every `@dataclass` / `Protocol` — wrong signal for this codebase. |
| **R0911** too-many-return-statements | **Exclude** | Fires on the intentional `cli.main` dispatch chain where each `if args.command == ...` branch is a return. Collapsing into dispatch tables breaks the test that statically verifies every `commands.handle_*` call receives `runtime_facade`. |

## Implementation

### R0801 — remove duplication at the source

The three largest duplicate blocks between `cli.py` and `runtime_facade.py`
were:

1. `resolve_goal_usage_updates` (183-line body).
2. `upsert_task` (141-line body).
3. `sync_usage` (83-line body) plus its `_resolve_cli_sync_usage_window` +
   `_apply_cli_auto_usage_updates` helpers.

Each cli-side function now delegates to its runtime_facade counterpart via
a lazy import (matching the `merge_tasks` pattern introduced in ARCH-020):

```python
def resolve_goal_usage_updates(**kwargs):
    from ai_agents_metrics import runtime_facade  # pylint: disable=import-outside-toplevel
    return runtime_facade.resolve_goal_usage_updates(**kwargs)
```

Tests that use positional-tuple destructuring (`*_, detected = cli.resolve_goal_usage_updates(...)`)
continue to pass because `runtime_facade` returns a `GoalUsageResolution`
NamedTuple, which IS-A tuple. Removed 400+ duplicated lines total.

Two smaller duplicated helpers (`ensure_active_task`, `resolve_usage_costs`)
also now delegate to runtime_facade.

The `ActiveTaskResolution` dataclass had two identical definitions (one in
`cli.py`, one in `runtime_facade.py`). Moved the single definition to
`git_state.py` (alongside `StartedWorkReport`) so both modules import it from
a shared source, which also resolves the mypy "incompatible return value
type" error between the two dataclasses.

Threshold kept at `min-similarity-lines=40`: at this setting all remaining
findings are zero.

### R0904 — `CommandRuntime` Protocol

Inline-disabled at the class level with a comment explaining that the
40-method count reflects the breadth of operations the CLI dispatches, not a
bug. Alternative (splitting into sub-Protocols) would fragment the single
`cli_module: CommandRuntime` type hint each `handle_*` function uses without
reducing the runtime surface they depend on.

### W0212 — `completion.py` argparse introspection

`completion.py` accesses `parser._actions` and `argparse._SubParsersAction` to
enumerate subcommands for bash/zsh completion. argparse provides no public
API for this — every third-party shell-completion library (argcomplete,
shtab) relies on the same private attributes, which are stable across
CPython 3.9–3.13.

Applied a **narrow module-level `# pylint: disable=protected-access`** with a
docstring documenting the justification. This is the minimum scope that
covers the three helpers that genuinely need the private API.

### W0212 — `cli.py` `_choices_actions` filter

One block in `build_parser` mutates `subparsers._choices_actions` to hide
advanced commands from the top-level `--help` output. argparse has no public
API to mark a subparser as hidden after creation. The block was duplicated
(same filter written twice back-to-back); collapsed into a single mutation
wrapped in a narrow `# pylint: disable=protected-access` / `# pylint: enable=protected-access`
block. The surrounding comment already documented the reason.

### Gate wiring

- `Makefile pylint-check` tier 3 gains `R0904,W0212,R0801` in the `--enable`
  list and `--min-similarity-lines=40` in the flag list.
- `pyproject.toml`:
  - `[tool.pylint."messages control"] enable` lists the three new codes.
  - `[tool.pylint.similarities] min-similarity-lines = 40` (new section).
  - Comment block documents why R0903 and R0911 are deliberately excluded.

## Acceptance Criteria

- [x] `make verify` blocks regressions on R0904, W0212, R0801.
- [x] The 400+ lines of duplicated business logic between cli.py and
      runtime_facade.py are removed (cli now delegates).
- [x] `ActiveTaskResolution` has a single definition (in `git_state.py`).
- [x] W0212 suppressions are scoped to the narrowest possible block and each
      has a documented reason.
- [x] R0903 and R0911 are explicitly marked as "intentionally excluded" in
      pyproject and ARCH-022.
- [x] Import-linter contracts stay at 6 kept / 0 broken.
- [x] `make verify` clean: tier 1 / tier 2 / tier 3 all 10/10.
