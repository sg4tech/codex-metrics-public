# ARCH-019: Globally enable pylint across the whole project

**Status:** done  
**Priority:** medium  
**Complexity:** medium

## Rationale

`pylint` is currently present in the repository, but only as a selective subset of rules and with large modules such as `cli.py`, `commands.py`, and `history/ingest.py` excluded from the gate.

That keeps `verify` practical today, but it also means we do not yet have a full-project `pylint` signal. As a result:

- architectural and maintainability warnings can remain invisible in excluded modules
- the team has no explicit plan for moving from partial coverage to global coverage
- it is too easy to confuse "pylint exists" with "pylint protects the whole codebase"

The goal of this task is not "turn on every rule immediately." The goal is to make full-project `pylint` feasible without drowning `verify` in legacy noise.

## Implementation

The `pylint-check` target now runs across the entire `src/` tree without any `--ignore` exclusions.

### What was blocking global coverage

| File | Violation | Resolution |
|------|-----------|------------|
| `cli.py` | W0611 unused-import | `# pylint: disable=unused-import` at module level — these are intentional re-exports already marked `# noqa: F401` for ruff; pylint does not honour `noqa` so an explicit disable is needed |
| `cli.py` | C0302 too-many-lines (1640) | `# pylint: disable=too-many-lines` — cli.py is a router/dispatcher/shim; splitting into per-command modules is a separate future task |
| `commands.py` | C0302 too-many-lines (1277) | `# pylint: disable=too-many-lines` — commands.py bundles all CLI command implementations; splitting is a tracked future task |
| `commands.py` | W0718 broad-exception-caught | `# pylint: disable=broad-exception-caught` inline — pricing load is optional fallback; broad catch is intentional |
| `history/ingest.py` | C0302 too-many-lines (1075) | `# pylint: disable=too-many-lines` — ingest.py handles all history ingestion stages; splitting into sub-stages is a tracked future task |

### Rule tiers

**Tier 1 — hard-fail (gates `verify`):**  
`E0401,E0602,E1101,E1120,W0102,W0611,W0612,W0718,W1203,R0401,C0302`

These rules catch real bugs and architectural violations (missing imports, undefined names, unused imports, method signature mismatches, mutable defaults, circular imports, file-size gate).

**Tier 2 — advisory (reported but does not block):**  
`R0912,R0913,R0914,R0915,R0902,W0401,C0411`

These rules surface complexity and style findings that are useful signal but currently produce many false positives in large data-centric modules. They are reported with `|| true` to inform without blocking.

### Next steps to improve coverage further

- **C0302 suppressions** can be removed when the three large files are split into smaller modules. This work is tracked but not yet scheduled.
- **Tier 2 advisory findings** are high in count across the codebase; a future task could triage them and promote stable signal rules to tier 1.

## Acceptance Criteria

- [x] Current `pylint` exclusions and their rationale are explicitly inventoried
- [x] Hard-fail vs advisory `pylint` rules are documented
- [x] There is a staged rollout plan for currently excluded modules
- [x] The next concrete unblocker for global `pylint` is identified
- [x] Repo docs reflect the intended target state
- [x] End state: full-project `pylint` is enabled in `verify`
