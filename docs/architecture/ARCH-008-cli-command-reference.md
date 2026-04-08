# ARCH-008: Write CLI command reference

**Priority:** medium
**Complexity:** low
**Status:** done

## Problem

The project has 40+ CLI commands. To understand what a specific command does, its flags, and its behaviour, you need to read argparse definitions in `cli.py`. This is expensive to do at the start of every session.

## Desired state

A `docs/cli-reference.md` file with a table of commands grouped by purpose:
- Task lifecycle (`start-task`, `continue-task`, `finish-task`)
- Metrics mutation (`update`, `create`, `merge-tasks`)
- Inspection (`show`, `show-goal`, `render-report`)
- History pipeline (`ingest-history`, `normalize-history`, `derive-history`, `compare-history`, `audit-history`)
- Sync (`sync-usage`)
- Tooling (`init`, `verify-public-boundary`, `export`, `render-completion`)

For each command: purpose, key flags, typical usage example.

## Acceptance criteria

- [x] All commands from `cli.py` are listed
- [x] Each command has a 1–2 line description and its main flags
- [x] Examples for the most frequently used commands
