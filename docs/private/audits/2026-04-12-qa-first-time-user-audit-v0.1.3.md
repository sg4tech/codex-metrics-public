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

### 6. README actively claims `history-update` reads both sources by default — false

The Quick Start says:

```
# Run the full history pipeline (reads ~/.codex + ~/.claude by default):
ai-agents-metrics history-update
```

This is wrong. Without `--source`, only `~/.codex` is read (`source_root: /Users/.../.codex` confirmed via `--json`). A Claude Code user who follows this instruction verbatim gets a warehouse with only Codex data and no explanation why Claude sessions are missing.

This is stronger than "default undocumented" — the README is actively making a false claim.

**Fix:** Correct the Quick Start comment and state the actual default.

**Decision:** Уже в работе в другом треде. **Fixed in master (2026-04-13):** default is now `all`, reads both `~/.codex` and `~/.claude`. Behaviour matches README.

### 9. Retry pressure = 0% for Codex-only data — headline metric broken on default source

After running `ai-agents-metrics history-update` (default: Codex), all 70 threads show `has_retry_pressure=0`, `attempt_count=1`. The "History signals" section reports:

```
Threads with retry pressure: 0 / 51 (0%)
```

After adding Claude history (`--source claude`), 25/108 threads show retry pressure (23%). The retry detection either does not work for Codex threads, or Codex sessions genuinely represent single-attempt threads (no continuation mechanism to detect). Either way:

- The main value-proposition metric is 0% on the default source
- The README example shows 32% — impossible to reproduce without Claude data
- No explanation is given in the output or docs

**Fix:** Either document that retry detection requires Claude history, or add a note to the `History signals` output when the Codex-only warehouse shows 0%.

**Decision:** Needs investigation and decision. **Partially mitigated (2026-04-13):** default source is now `all` so Claude history is included automatically — retry pressure will be non-zero for users who have Claude sessions. Root cause (Codex retry detection not implemented) is still open.

### 10. `finish-task` with non-existent task ID gives cryptic error

```bash
$ ai-agents-metrics finish-task --task-id 2026-01-01-999 --status success
Error: title is required when creating a new task
```

The tool attempts to create a new goal instead of rejecting the unknown ID. The error message exposes internal logic ("creating a new task") instead of the user-facing problem ("goal not found").

**Fix:** Validate that `--task-id` refers to an existing goal before proceeding; return `Error: Goal 2026-01-01-999 not found.`

**Decision:** Needs fix.

### 11. `--source all` is a valid internal choice but hidden from `--help`

The argparse definition in the dev source has `choices=["codex", "claude", "all"]`, but `--help` shows only `{codex,claude}`. A user cannot discover `--source all` from the CLI. The behaviour is also internally inconsistent: without `--source`, the code routes to `all`; but passing `--source all` explicitly is rejected by the installed binary.

**Fix:** Either expose `all` in `--help` or remove it from the internal choices and route to multi-source via the no-flag default path only.

**Decision:** **Fixed in master (2026-04-13):** `--source all` is now visible in `--help` with description "reads both ~/.codex and ~/.claude". Explicit `--source all` is accepted and works correctly.

### 7. `show` without prior `history-update` — silent zeros, no hint

When no warehouse exists, `show` omits the "History signals" section entirely with no explanation. A new user who skips `history-update` or runs `show` from a different directory sees zeros everywhere and has no indication why.

**Fix:** Print "History signals: not available / Run 'ai-agents-metrics history-update'..." when warehouse is absent. Add a Tip when warehouse exists but has no data for the current directory.

**Decision:** **Fixed in master (2026-04-13):** `reporting.py` now prints the hint when `history_signals is None`, and a Tip line when showing all-projects fallback.

### 8. `render-html` output notation unexplained

Output includes `(retry: warehouse, tokens: warehouse)` or `(retry: ledger, tokens: ledger)`. This distinction is not documented in the README or in the command output itself. A new user does not know whether "warehouse" or "ledger" is better.

**Fix:** Add a one-line explanation to the README `render-html` section.

**Decision:** Пока не ясно. Не правим, разберёмся позже.

### 9. Warehouse size not mentioned

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
| `history-update` (no flag) | PASS (defaults to all) | Fixed in master 2026-04-13 — reads both sources |
| `show` | PASS | Shows hint to run history-update when warehouse absent — fixed in master 2026-04-13 |
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
