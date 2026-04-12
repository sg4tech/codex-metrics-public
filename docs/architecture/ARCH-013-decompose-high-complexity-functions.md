# ARCH-013: Decompose high-complexity orchestrator functions

**Status:** open  
**Priority:** high  
**Complexity:** high

## Rationale

Two functions have extreme cyclomatic complexity (rank F) identified by radon (ARCH-011):

| Function | File | Complexity |
|----------|------|------------|
| `derive_codex_history` | `history_derive.py:490` | F (85) |
| `aggregate_report_data` | `_report_aggregation.py:126` | F (70) |

These are monolithic orchestrators that combine dispatch logic, data transformation, and error handling in a single body. At CC=85 and CC=70, they are effectively untestable in isolation and extremely hard to reason about.

## Goals

- Reduce both functions to rank B or below (CC ≤ 10) by extracting named sub-functions
- Each extracted sub-function should have a single clear responsibility
- Existing tests must continue to pass without modification of test intent
- New unit tests should be added for each extracted sub-function

## Approach

### `derive_codex_history` (CC=85, `history_derive.py:490`)

Identify the major phases inside the function (e.g. session loading, event construction, goal matching, deduplication, output assembly) and extract each into a named helper. The outer function becomes an orchestrating sequence of calls.

Suggested extraction targets:
- Session loading and validation
- Per-event transformation
- Goal matching / attribution logic
- Deduplication / supersedes handling
- Output assembly

### `aggregate_report_data` (CC=70, `_report_aggregation.py:126`)

The file is only 318 lines with one dominant function — it is doing too much. Extract aggregation phases into focused helpers:
- Token/cost series assembly
- Retry pressure computation
- Goal-type breakdown
- Date bucketing and alignment

## Acceptance Criteria

- [ ] `radon cc src/ai_agents_metrics/history_derive.py -s` shows `derive_codex_history` ≤ B (CC ≤ 10)
- [ ] `radon cc src/ai_agents_metrics/_report_aggregation.py -s` shows `aggregate_report_data` ≤ B (CC ≤ 10)
- [ ] `make verify` passes without regressions
- [ ] New unit tests cover at least the major extracted sub-functions
- [ ] No change to public API or CLI behaviour
