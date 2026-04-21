# ARCH-019: Globally enable pylint across the whole project

**Status:** planned  
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

1. Inventory the current blockers to full-project `pylint`:
   - excluded modules
   - warning classes that are mostly signal vs mostly noise
   - findings that belong in `ruff`, `mypy`, or `import-linter` instead
2. Split the rule set into:
   - hard-fail rules that should gate `verify`
   - advisory rules that should report but not block
3. Create a staged rollout plan for currently excluded modules:
   - define the order
   - define the minimal cleanup needed per module
   - avoid mixing this with unrelated refactors
4. Reduce or document the highest-noise findings that would make global enablement impractical
5. Update docs and verification targets so the intended end state is explicit

## Acceptance Criteria

- [ ] Current `pylint` exclusions and their rationale are explicitly inventoried
- [ ] Hard-fail vs advisory `pylint` rules are documented
- [ ] There is a staged rollout plan for currently excluded modules
- [ ] The next concrete unblocker for global `pylint` is identified
- [ ] Repo docs reflect the intended target state
- [ ] End state is one of:
  - [ ] full-project `pylint` is enabled in `verify`
  - [ ] a documented staged rollout exists and the repository is aligned to it

