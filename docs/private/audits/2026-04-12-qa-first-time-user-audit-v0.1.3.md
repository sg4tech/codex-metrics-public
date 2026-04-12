# QA Audit: First-Time User Experience (PyPI 0.1.3)

**Date:** 2026-04-12
**Method:** Installed `ai-agents-metrics 0.1.3` from PyPI via `pipx`, followed README instructions from scratch as a new user. Tested all commands mentioned in the README.
**Environment:** macOS, Python 3.14, zsh
**Test directory:** `/tmp/qa-test-metrics/` (fresh, non-production)

---

## Critical (P0)

### 1. `show --json` warning pollutes stdout — breaks JSON consumers

When `show --json` is run outside a git repository, the warning:

```
Warning: unable to detect started work reliably in this repository.
```

is printed to **stdout** instead of stderr. This makes the output invalid JSON:

```bash
ai-agents-metrics show --json 2>/dev/null | python3 -c "import sys,json; json.load(sys.stdin)"
# → JSONDecodeError
```

**Impact:** Any agent, script, or tool that pipes `show --json` to a JSON parser will break silently in non-git directories. This is the primary machine-consumption path.

**Fix:** Route the warning to stderr.

**Decision:** Fix. → будем делать. **Fixed in master (CODEX-62).**

---

## Serious (P1)

### 2. `completion zsh` outputs stale internal name

`ai-agents-metrics completion zsh` outputs `#compdef codex-metrics` as the first line. This is the old internal tool name. A user who installs this literally will not get zsh completion for `ai-agents-metrics`.

**Fix:** Update the compdef header to `ai-agents-metrics`.

**Decision:** Fix. → будем делать. **Fixed in master (CODEX-63).**

### 3. `finish-task` on an already-closed goal succeeds silently

Calling `finish-task` on an already-closed task ID re-closes it with a new `finished_at` timestamp. No error, no warning. A user who fat-fingers a task-id or double-submits a command silently corrupts their ledger.

**Fix:** Reject `finish-task` on goals that are already in a terminal state (`success` or `fail`).

**Decision:** Won't fix. Оставляем как есть.

---

## UX Issues (P2)

### 4. Mutation commands print full 50-line summary (carry-over from v0.1.2)

`start-task`, `continue-task`, `finish-task` each dump the full metrics summary. The useful confirmation line is buried at the bottom. No `--quiet` flag exists. (Same issue as P2.6 in the v0.1.2 audit — still not fixed.)

**Decision:** Пока не правим. Идея интересная, возможно будем делать позже.

### 5. `history-compare` fails hard without actionable hint

When run before `history-update`, exits with code 1:

```
Error: Warehouse does not exist: metrics/.ai-agents-metrics/warehouse.db
```

The error message does not suggest the fix. A new user following the README but running steps out of order gets an opaque failure.

**Fix:** Append `Run 'ai-agents-metrics history-update' first.` to the error message.

**Decision:** Fix. → будем делать. **Fixed in master (CODEX-64).**

### 6. Default `--source` is `codex` — not stated explicitly in README

The Quick Start correctly shows `--source claude` for Claude Code users, but the default is never stated. A Claude Code user who runs `ai-agents-metrics history-update` without the flag gets a silently empty or wrong warehouse.

**Fix:** Add one line to Quick Start: "Default source is `codex`. Use `--source claude` for Claude Code."

**Decision:** Уже в работе в другом треде.

### 7. `render-html` output notation unexplained

Output includes `(retry: warehouse, tokens: warehouse)` or `(retry: ledger, tokens: ledger)`. This distinction is not documented in the README or in the command output itself. A new user does not know whether "warehouse" or "ledger" is better.

**Fix:** Add a one-line explanation to the README `render-html` section.

**Decision:** Пока не ясно. Не правим, разберёмся позже.

### 8. Warehouse size not mentioned

On a moderately active Claude Code install (~157 session files), the warehouse is 333 MB. The README says "all data stays local" but gives no storage guidance.

**Fix:** Add a note on typical storage footprint.

**Decision:** Пока не ясно. Возможно сделаем.

---

## What works well

- `history-update --source claude` works from any directory, no prior setup needed — core value prop is intact
- `show`, `render-html`, `audit-cost-coverage`, `history-audit` all handle zero-data gracefully
- Bootstrap is idempotent and accurate in dry-run mode
- Full manual tracking lifecycle (`start-task` → `continue-task` → `finish-task`) works correctly
- Validation is solid: `--status fail` without `--failure-reason` is caught with a clear domain error
- `--help` at all levels is complete and informative
- `history-update` prints stage-by-stage progress (ingest → normalize → derive)
- `render-html` produces a valid self-contained HTML file with no external dependencies
- JSON mode (`show --json`, `history-update --json`) exists — except for the stdout-pollution bug above

---

## Summary table

| Command | Result | Notes |
|---|---|---|
| `--help` / `--version` | PASS | Clear, complete |
| `history-update --source claude` | PASS | Works from any dir |
| `history-update` (no flag) | PASS (defaults to codex) | Default undocumented — P2 |
| `show` | PASS | Works empty and with data |
| `show --json` (outside git) | FAIL | Warning on stdout, invalid JSON — P0 |
| `bootstrap --dry-run` | PASS | Accurate preview |
| `bootstrap` | PASS | Idempotent |
| `start-task` | PASS | |
| `continue-task` | PASS | |
| `finish-task` (first close) | PASS | |
| `finish-task` (already closed) | FAIL | Silent re-close — P1 |
| `audit-cost-coverage` | PASS | Clear diagnostic |
| `render-html` | PASS | Valid self-contained HTML |
| `ensure-active-task` (no git) | PASS | Clear no-op message |
| `history-compare` (with warehouse) | PASS | Useful output |
| `history-compare` (no warehouse) | MODERATE | Hard exit, no fix hint — P2 |
| `history-ingest/normalize/derive` | PASS | Individual stages work |
| `completion zsh` | FAIL | `#compdef codex-metrics` — P1 |
| `render-report` | PASS | |
| `sync-usage` | PASS | |
| `history-audit` | PASS | |
