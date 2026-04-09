# Plan: Event Sourcing Storage Migration

## Status

- Draft date: `2026-04-06`
- Related hypothesis: [H-030](../product-hypotheses/archive/H-030.md)
- Branch: `feature/event-sourcing-storage` (to be created)
- PR strategy: one big PR
- Linear: no issue yet (no CLI access at time of writing; create manually before starting)
- Scope: this private repo only; public overlay (H-023) gets it when that repo is created

## Goal

Replace `metrics/codex_metrics.json` (mutable, git-tracked, uchg-flagged) with an append-only event log `metrics/events.ndjson` as the canonical storage. Remove the mutable file from git. Derived state (current goals, entries, summary) is computed in-memory at runtime — never persisted to disk.

## Decisions already made

| Decision | Choice | Rationale |
|---|---|---|
| Canonical storage format | `metrics/events.ndjson` (newline-delimited JSON) | append-only → no git merge conflicts |
| `codex_metrics.json` after migration | removed from git entirely | no value as a persistent artifact once event log is canonical |
| Derived state persistence | none — in-memory only | eliminates the merge conflict class at the source |
| Migration of existing 235 goals | deferred — not migrated | history accessible via `git log` on old file; start fresh from cutover |
| Public overlay (H-023) | deferred — do this repo first | public repo doesn't exist yet |

## Event schema

Each line in `events.ndjson` is a JSON object:

```json
{
  "event_id": "<uuid4>",
  "occurred_at": "<ISO 8601>",
  "event_type": "goal_snapshot" | "entry_snapshot" | "store_initialized" | "goals_merged",
  "command": "<cli command that triggered this>",
  "goal": { ...full GoalRecord fields... },     // present for goal_snapshot
  "entry": { ...full AttemptEntryRecord fields... }, // present for entry_snapshot
  "merged_from_goal_id": "..."                  // present for goals_merged
}
```

**Replay algorithm** (O(n) over events):
1. Scan all lines; for `goal_snapshot` events: `goals[goal_id] = event.goal` (last write wins)
2. Same for `entry_snapshot`: `entries[entry_id] = event.entry`
3. Compute `summary` by aggregating over final goal states
4. Return `MetricsData(goals=list(goals.values()), entries=list(entries.values()), summary=...)`

This is intentionally simple. No event sourcing ceremony — just append + last-write-wins projection.

---

## Implementation phases

### Phase 1 — Event append layer

**New file:** `src/codex_metrics/event_log.py`

- `EventRecord` dataclass: `event_id`, `occurred_at`, `event_type`, `command`, `goal`, `entry`, `merged_from_goal_id`
- `append_event(path: Path, event: EventRecord) -> None`
  - opens file in append mode
  - writes one JSON line + `\n`
  - uses `fcntl` lock (same as current `metrics_mutation_lock`) to guard concurrent appends
  - no uchg flag needed — file is append-only, never replaced

**Tests:**
- append single event → file contains 1 line
- append multiple events → all lines present, order preserved
- concurrent append (two processes) → no data loss, all lines readable
- invalid JSON in file → does not crash append (append is independent of replay)

---

### Phase 2 — Projection layer

**New file:** `src/codex_metrics/projection.py`

- `replay_events(path: Path) -> MetricsData`
  - reads `events.ndjson`, builds in-memory state via last-write-wins per goal_id / entry_id
  - returns same `MetricsData` structure as current `load_metrics()` so downstream is a drop-in swap
  - if file doesn't exist: returns `default_metrics()` (same behavior as current)
  - skips malformed lines with a warning (resilience)

- `compute_summary(goals: list[GoalRecord], entries: list[AttemptEntryRecord]) -> dict`
  - extracted from current domain logic; made a standalone function
  - summary is never stored, always recomputed from final goal states

**Tests:**
- empty file → returns default metrics
- single `goal_snapshot` event → goal appears in output
- two `goal_snapshot` events for same goal_id → last one wins
- `store_initialized` event → handled without error
- `goals_merged` event → reflected in goal state
- summary computed correctly from goal list

---

### Phase 3 — Migrate write commands

Replace the `load → mutate → save_metrics()` pattern in each command handler with `replay_events() → validate → append_event()`.

**Commands to migrate** (all in `src/codex_metrics/commands.py` and `cli.py`):

| Command | Current write | New write |
|---|---|---|
| `init` | `save_metrics()` with empty structure | append `store_initialized` event |
| `bootstrap` | `save_metrics()` | append `store_initialized` event |
| `start-task` | load → add goal → save | append `goal_snapshot` (status=in_progress) |
| `continue-task` | load → update goal → save | append `goal_snapshot` (incremented attempts) |
| `finish-task` | load → update goal → save | append `goal_snapshot` (status=success/fail) + `entry_snapshot` |
| `ensure-active-task` | load → create/update → save | append `goal_snapshot` |
| `sync-usage` | load → update tokens/cost → save | append `goal_snapshot` per updated goal |
| `sync-codex-usage` | load → update tokens/cost → save | append `goal_snapshot` per updated goal |
| `merge-tasks` | load → merge → save | append `goals_merged` + `goal_snapshot` for surviving goal |
| `update` | load → update fields → save | append `goal_snapshot` |

Each handler becomes: `state = replay_events(path)` → validate/compute new goal state → `append_event(path, ...)`.

**Important:** Read commands (`show`, `render-report`, `audit-cost-coverage`, etc.) only need their `load_metrics(path)` call replaced with `replay_events(path)`. No other changes.

---

### Phase 4 — Remove old storage artifacts

After all commands are migrated and tests pass:

1. `git rm metrics/codex_metrics.json` — remove from tracking
2. Add `metrics/codex_metrics.json` to `.gitignore` (in case it lingers locally after checkout)
3. Delete `src/codex_metrics/file_immutability.py`
4. Delete `tests/test_storage_immutability.py`
5. Remove `metrics_file_immutability_guard()` call from `storage.py`
6. Remove `storage.save_metrics()` once no callers remain
7. Update `storage.load_metrics()` → delegate to `projection.replay_events()` or remove entirely

---

### Phase 5 — Update `init` and bootstrap flow

- `init` command: if `metrics/events.ndjson` already exists → safe to rerun (idempotent, just appends `store_initialized`); if it doesn't exist → create file + append event
- `bootstrap` command: same logic
- `--dry-run` support: replay without writing, print what would be appended

---

### Phase 6 — Update tests

- `tests/test_storage_roundtrip.py` → replace with roundtrip test for `append_event` + `replay_events`
- `tests/test_storage_immutability.py` → delete (behavior no longer exists)
- `tests/test_update_codex_metrics.py` → update fixtures to use event log format
- `tests/test_observability.py` → update if observability hooks still fire (they should; observability is separate from storage)
- Add regression test: `git pull` does not fail on `events.ndjson` (append-only property)

---

### Phase 7 — AGENTS.md and policy updates

- Remove the rule about never running `chflags nouchg` (no longer relevant)
- Add rule: `metrics/events.ndjson` is append-only — never edit lines in place
- Update `docs/codex-metrics-policy.md` if it references `codex_metrics.json`
- Update `AGENTS.md` metrics tooling section

---

## What this is NOT doing

- No migration of existing 235 goals into event format — history stays in git log of old file
- No changes to the observability SQLite layer (`events.sqlite`) — it remains a separate side-channel log
- No changes to the read-only history pipeline (`history_ingest.py`, `history_normalize.py`, etc.)
- No public overlay work — deferred until H-023 is executed

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Two agents append to the exact same byte position simultaneously | fcntl lock guards appends; same as current mutex |
| Replay latency grows as log grows | acceptable for current scale (~few hundred events/year); revisit at 10k+ events |
| Malformed line from a crash mid-write | atomic line append (write full line + newline before releasing lock); skip-on-error in replay |
| Old tooling that expects `codex_metrics.json` to exist | `load_metrics()` wrapper stays as a shim delegating to `replay_events()` during transition |

## Validation checklist (before PR)

```bash
make verify
./tools/codex-metrics show
./tools/codex-metrics start-task --title "test" --goal-type meta
./tools/codex-metrics finish-task --status success
./tools/codex-metrics show
# verify events.ndjson has lines, codex_metrics.json is gone
git add metrics/events.ndjson && git status
# verify no conflicts possible on events.ndjson
```
