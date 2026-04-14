# ARCH-013: Decompose high-complexity orchestrator functions

**Status:** open  
**Priority:** high  
**Complexity:** high

## Rationale

Two functions had extreme cyclomatic complexity (rank F) identified by radon (ARCH-011).
One has been substantially reduced via a module split; the other remains unaddressed.

| Function | File | Original CC | Current CC | Target |
|----------|------|-------------|------------|--------|
| `derive_codex_history` | `history/derive.py:48` | F (85) | C (15) | ≤ B (10) |
| `aggregate_report_data` | `_report_aggregation.py:126` | F (70) | F (70) | ≤ B (10) |

## Progress

### `derive_codex_history` — partially done

`history_derive.py` was split into four modules:

- `history/derive.py` — orchestrator (derive_codex_history, CC=15)
- `history/derive_build.py` — data structure construction (all helpers ≤ B)
- `history/derive_insert.py` — database insertion logic (max CC=18 in `_insert_attempts_and_session_usage`)
- `history/derive_schema.py` — schema definitions

CC dropped from 85 → 15. The original rank-F monolith is gone. Remaining work: bring
`derive_codex_history` from C (15) to B (≤10), and reduce `_insert_attempts_and_session_usage`
(CC=18) and `_insert_message_facts` (CC=14) in `derive_insert.py`.

### `aggregate_report_data` — not started

CC remains F (70). Two helpers have already been extracted (`_aggregate_warehouse_tokens` CC=11,
`_aggregate_warehouse_retry` CC=9), but the main function body is unchanged.

## Goals

- Reduce both functions to rank B or below (CC ≤ 10) by extracting named sub-functions
- Each extracted sub-function should have a single clear responsibility
- Existing tests must continue to pass without modification of test intent
- New unit tests should be added for each extracted sub-function

## Approach

### `derive_codex_history` (CC=15, `history/derive.py:48`)

The outer orchestrator is close to the target. Extract the remaining conditional dispatch
and loop bodies into named helpers so the top-level reads as a sequence of named steps.

### `_insert_attempts_and_session_usage` (CC=18, `history/derive_insert.py:152`)
### `_insert_message_facts` (CC=14, `history/derive_insert.py:93`)

Both insertion helpers combine query construction, data transformation, and conditional
branching. Extract per-record transformation logic into focused sub-functions.

### `aggregate_report_data` (CC=70, `_report_aggregation.py:126`)

Extract aggregation phases into focused helpers:
- Token/cost series assembly
- Goal-type breakdown
- Date bucketing and alignment
- Summary stats (the remaining conditional branches)

## Acceptance Criteria

- [ ] `radon cc src/ai_agents_metrics/history/derive.py -s` shows `derive_codex_history` ≤ B (CC ≤ 10)
- [ ] `radon cc src/ai_agents_metrics/history/derive_insert.py -s` shows all functions ≤ B (CC ≤ 10)
- [ ] `radon cc src/ai_agents_metrics/_report_aggregation.py -s` shows `aggregate_report_data` ≤ B (CC ≤ 10)
- [ ] `make verify` passes without regressions
- [ ] New unit tests cover at least the major extracted sub-functions
- [ ] No change to public API or CLI behaviour
