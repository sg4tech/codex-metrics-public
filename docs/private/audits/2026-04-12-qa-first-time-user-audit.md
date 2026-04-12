# QA Audit: First-Time User Experience (PyPI 0.1.2)

> **Status:** Superseded by [v0.1.3 audit](./2026-04-12-qa-first-time-user-audit-v0.1.3.md). P0 and P1 issues below are fixed in v0.1.3.

**Date:** 2026-04-12
**Method:** Installed `ai-agents-metrics 0.1.2` from PyPI via `pipx`, followed README instructions from scratch as a new user.
**Environment:** macOS, Python 3.14, zsh

---

## Critical (P0)

### ~~1. `bootstrap` crashes with FileNotFoundError~~ ✓ Fixed in v0.1.3

`ai-agents-metrics bootstrap --target-dir . --dry-run` produces a traceback:

```
FileNotFoundError: .../ai_agents_metrics/data/bootstrap_codex_metrics_policy.md
```

**Root cause:** `data/bootstrap_codex_metrics_policy.md` is not included in the PyPI sdist/wheel. Only `model_pricing.json` is present in `site-packages/ai_agents_metrics/data/`.

**Impact:** The entire "Bootstrap a Repository" section of the README is broken for PyPI users.

### ~~2. `show` displays 0 threads after `history-update`~~ ✓ Fixed in v0.1.3

Quick Start promises: `history-update` → `show` → see your data. In practice:

- `history-update` reports "115 threads imported"
- `show` outputs "Project threads: 0"

**Root cause:** `show` filters `derived_projects` by `parent_project_cwd = current working directory`. The warehouse contains the original project paths from `~/.codex`/`~/.claude` (e.g. `/Users/viktor/PycharmProjects/codex-metrics`). If the user runs `show` from a different directory (e.g. `/tmp/test-repo`), zero rows match.

**Impact:** The main value proposition of Quick Start fails silently — the user sees zeros everywhere and has no indication why.

---

## Serious (P1)

### ~~3. `pip install` fails on modern macOS~~ ✓ Fixed in v0.1.3

README says `pip install ai-agents-metrics`. On macOS with PEP 668 (Python 3.12+), this produces:

```
error: externally-managed-environment
```

**Fix needed:** Document `pipx install ai-agents-metrics` or `pip install --user ai-agents-metrics` as alternatives.

### ~~4. Documented warehouse path does not match reality~~ ✓ Fixed in v0.1.3

- **README says:** `.ai-agents-metrics/warehouse.db`
- **Actual path:** `metrics/.ai-agents-metrics/codex_raw_history.sqlite`

Two mismatches: the `metrics/` prefix and the filename.

### ~~5. Warehouse filename is source-agnostic but shouldn't be~~ ✓ Fixed in v0.1.3

`history-update --source claude` writes to `codex_raw_history.sqlite`. Confusing given the "agent-agnostic" positioning and the fact that source is claude.

---

## UX Issues (P2)

### 6. Mutation commands dump full summary *(still open in v0.1.3)*

`start-task`, `continue-task`, `finish-task` each print 40+ lines of summary (mostly `n/a`). The useful confirmation ("Updated goal 2026-04-12-001, Status: in_progress, Attempts: 1") is buried. Expected: brief confirmation; full summary via `show`.

### 7. `init` command not documented in README

Present in `--help` but absent from README. Useful as a lightweight alternative to `bootstrap` for users who only want the event log without the full scaffold.

### 8. Error output ordering on invalid `--source-root`

```
Error: Source root does not exist: /nonexistent
==> history-ingest
```

The error appears before the stage banner, making it look like it came from a different stage.

---

## What works well

- `history-update` reliably parses both codex and claude history
- `start-task` → `continue-task` → `finish-task` lifecycle works correctly
- `render-html` produces a self-contained HTML file
- `audit-cost-coverage` and `history-audit` give useful diagnostics
- `--help` text is high quality and informative
- Error messages for missing source roots are clear
- `--version` works

---

## Recommendation

The #1 priority is fixing the Quick Start path. A user who installs, runs `history-update` + `show`, and sees zeros will leave. Options:

1. Make `show` project-agnostic by default (show all warehouse data), with `--project` to filter
2. Add `show --all` flag
3. At minimum, explain in README that `show` is per-project and must be run from a tracked project directory
4. Print a hint when `show` finds warehouse data but zero matching projects: "Warehouse contains N threads across M projects. Run from one of those project directories to see results, or use --all."

The `bootstrap` crash is a packaging bug — fix `pyproject.toml` to include all `data/*.md` files.
