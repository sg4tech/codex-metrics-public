# ARCH-012: Integrate import-linter for architectural boundary enforcement

**Status:** done  
**Priority:** medium  
**Complexity:** low

## Rationale

As the codebase grows, ensuring that module dependencies respect architectural layers becomes critical. `import-linter` (formerly `architectural-boundaries`) allows defining explicit rules:
- Forbid circular imports between specific modules
- Enforce layer separation (e.g., domain cannot import from CLI)
- Prevent implementations from importing from private submodules
- Make architectural constraints explicit and testable

Current state: No automated architectural boundary checks; boundaries are enforced only through code review.

## Implementation

1. Add `import-linter` to dev dependencies in `pyproject.toml`
2. Create `.importlinter` configuration file defining architectural rules:
   - CLI layer → should not import from reporting/history pipelines except via public API
   - Domain layer → should not import from storage or CLI
   - History pipeline → internal modules should not be imported from outside
   - No circular dependencies between any of: domain, storage, CLI, reporting
3. Add `import-linter check` to `Makefile` (under `quality` target or extended `verify`)
4. Integrate into pre-push hook or CI
5. Document the ruleset in `AGENTS.md` or architecture.md under "Layer Boundaries"

## Acceptance Criteria

- [ ] `import-linter` is installed and configured
- [ ] Configuration file defines at least 4 architectural rules
- [ ] `import-linter check` runs without errors on current codebase
- [ ] All current code passes the rules (baseline established)
- [ ] `make quality` (or `make verify`) runs import-linter checks
- [ ] At least one rule is tested (e.g., add a test that validates CLI cannot directly import from history internals)
- [ ] Documentation of layer boundaries added to architecture.md
