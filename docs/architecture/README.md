# Architecture Tasks

Technical debt and structural improvements not tied to specific product features.

Each file is a standalone task. When picked up, create a Linear issue and commit via `CODEX-NNN:`.

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
| [ARCH-011](ARCH-011-radon-metrics.md) | Integrate radon for code complexity metrics | medium | low | in-progress |
| [ARCH-012](ARCH-012-import-linter.md) | Integrate import-linter for architectural boundary enforcement | medium | low | done |
| [ARCH-013](ARCH-013-decompose-high-complexity-functions.md) | Decompose high-complexity orchestrator functions (derive_codex_history, aggregate_report_data) | high | high | open |
| [ARCH-014](ARCH-014-extract-usage-resolution-from-cli.md) | Extract usage resolution functions out of cli.py (eliminate lazy circular imports) | medium | medium | open |
| [ARCH-015](ARCH-015-sqlalchemy-migration.md) | Migrate from raw sqlite3 to SQLAlchemy Core | medium | high | planned |

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
12. **ARCH-014** — medium priority; lazy `cli` imports in `usage_backends` and `commands` are a circular dep workaround; unblock import-linter contract after fix
13. **ARCH-015** — medium priority; replace raw sqlite3 SQL strings with SQLAlchemy Core for safer, composable queries as complexity grows
