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
| [ARCH-006](ARCH-006-pipeline-typed-contracts.md) | Add typed contracts between pipeline stages | medium | medium | open |
| [ARCH-007](ARCH-007-legacy-supersedes-map.md) | Remove LEGACY_GOAL_SUPERSEDES_MAP from domain.py | low | low | open |
| [ARCH-008](ARCH-008-cli-command-reference.md) | Write CLI command reference | medium | low | open |
| [ARCH-009](ARCH-009-subprocess-coverage.md) | Automate subprocess coverage without manual env toggle | low | low | open |

## Recommended order

1. ~~**ARCH-001**~~ ✓ ~~**ARCH-005**~~ ✓
2. ~~**ARCH-004**~~ (obsolete) and **ARCH-007** — isolated, can be picked up at any time
3. ~~**ARCH-002**~~ ✓ — domain/ package complete
4. ~~**ARCH-003**~~ ✓ — timestamps are `datetime` in all dataclasses
5. **ARCH-006** — independent, but requires familiarity with the pipeline
