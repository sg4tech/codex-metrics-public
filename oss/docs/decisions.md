# Decision Log

**What this document is:** Key architectural and design decisions — why things are the way they are.

**When to read this:**
- Wondering why a particular design choice was made
- Considering a change that touches storage, locking, or the data model
- Reviewing the known trade-offs and tracked weaknesses

**Related docs:**
- [architecture.md](architecture.md) — what the system looks like now
- [architecture/README.md](architecture/README.md) — tracked technical debt (ARCH-001 through ARCH-009)

---

## Summary

New entries should follow the format below. Add entries as decisions are made or recalled — not just for new work, but also when the reasoning behind existing choices becomes clear.

```
## Decision title

**Context:** Why this decision was needed.

**Decision:** What was decided.

**Trade-offs:** Known costs or limitations.
```

---

## Append-only NDJSON event log, not a mutable JSON file

**Context:** The tool tracks metrics for AI agent tasks across parallel git worktrees. The data needs to be stored persistently without causing merge conflicts.

**Decision:** `metrics/events.ndjson` is the source of truth — an append-only NDJSON log where each CLI command adds one line. State is reconstructed at read time by replaying all events in file order, last-write-wins per `goal_id` / `entry_id`. The summary is always computed in-memory; it is never stored.

**Trade-offs:**
- Read-time replay adds a small cost on every `load_metrics` call (acceptable for hundreds of goals).
- The `tasks` / `goals` legacy alias is normalised in-memory during replay, not persisted.

**Supersedes:** the earlier decision to use `metrics/ai_agents_metrics.json` as a mutable JSON file (removed from git tracking; added to `.gitignore`).

**Why this works:** Append-only log eliminates git merge conflicts — parallel worktrees each append new lines, and `git merge` can automatically concatenate them without conflict. Human-readable and git-diffable. Replay is deterministic and can be inspected independently.

---

## fcntl for cross-process locking, not threading.Lock

**Context:** Multiple CLI invocations may run concurrently against the same `events.ndjson`.

**Decision:** `storage.metrics_mutation_lock` uses `fcntl.flock`.

**Trade-offs:** `fcntl` is POSIX-only — no Windows support. Acceptable because the tool targets macOS/Linux developer environments.

**Why this works:** The tool runs as short-lived CLI processes, not a long-lived server. Concurrent access comes from multiple processes, not threads within one process. `fcntl.flock` works across processes; `threading.Lock` does not.

---

## History pipeline as a separate SQLite warehouse

**Context:** Codex agent stores session history in `~/.codex/state_5.sqlite` and `~/.codex/logs_1.sqlite`. The tool needs to derive goal history from this raw data.

**Decision:** A three-stage pipeline (ingest → normalize → derive) with an intermediate SQLite warehouse at `.ai-agents-metrics/warehouse.db`, separate from the primary JSON store.

**Trade-offs:** Inter-stage contracts exist only as SQLite column names, not Python types (tracked in ARCH-006).

**Why this works:**
- Raw source data is large and noisy; normalisation and derivation are expensive.
- The warehouse acts as a cache — the pipeline can be re-run without re-reading the source.
- Each stage has a single responsibility and can be tested independently.
- Derived results can be compared against the NDJSON log without mutating it.

---

## Timestamps stored as ISO strings in the event log

**Context:** `GoalRecord` and `AttemptEntryRecord` have `started_at` and `finished_at` fields that must round-trip through JSON.

**Decision:** Timestamps are stored as ISO 8601 strings in `events.ndjson`. In-memory Python representation is `datetime | None`, parsed and serialised exclusively in `domain/serde.py`.

**Trade-offs:** Two parse functions exist (`parse_iso_datetime` and `parse_iso_datetime_flexible`) because input format is not normalised at the boundary. This is a known weakness tracked in ARCH-003.

**Why this works:** ISO strings serialise directly to JSON without a custom encoder and remain human-readable in the event log.

---

## HTML report uses warehouse as primary source for token and retry data

**Context:** `render-html` initially read all four charts from the ndjson ledger. The ledger starts at the first manually-tracked goal (2026-04-07); the warehouse covers all sessions from the first ingest (2026-03-31). Three of four charts showed only ~4 days of history, while full project history was available in the warehouse.

**Decision:** Charts 2 (Retry Pressure) and 3 (Token Cost) are warehouse-first: they query `derived_goals` JOIN `derived_session_usage` for per-thread token counts and retry counts. The ledger remains the sole source for Charts 1 and 4, which require `goal_type` and `cost_usd` — fields only present in manually-tracked goals.

**Trade-offs:**
- When the warehouse is absent, charts 2 and 3 fall back to ledger data (same pattern already used before this change).
- Sessions with unknown model pricing contribute $0 to the cost chart rather than corrupting it with raw token counts.
- Chart 1 (goal type breakdown) still only covers ledger history until auto-classification (H-036) is implemented.

**Why this works:** The warehouse has full token breakdown per thread back to first ingest with no migration needed. The inconsistency between ledger and warehouse date ranges is surfaced as an explicit UX feature via section headers ("Goals Ledger" vs "Session History") rather than hidden.

---

## html_report.py split into four focused modules

**Context:** `html_report.py` grew to 1084 lines as the HTML template, aggregation logic, date helpers, and public API accumulated in one file. Diffs and code review were impractical; the ~730-line template string dominated the file.

**Decision:** The file is split into:
- `_report_buckets.py` — pure date/bucket helpers (no I/O, no side effects)
- `_report_aggregation.py` — all aggregation logic; `_apply_token_pricing` extracted to eliminate duplication between the warehouse and ledger token paths
- `_report_template.py` — the HTML/CSS/JS template string (inert data, no Python logic)
- `html_report.py` — thin 37-line facade; public API (`aggregate_report_data`, `render_html_report`) unchanged

**Trade-offs:** Three new private modules with underscore-prefixed names. Tests import from the sub-modules directly.

**Why this works:** Each module has exactly one reason to change. The public import surface is preserved; `commands.py` and any downstream code importing from `html_report` requires no changes.

---

## cli.py as a re-export facade

**Context:** Early in the project, external scripts and tests imported symbols directly from `cli.py` before the module structure was stable.

**Decision:** `cli.py` re-exports ~50 symbols from `domain`, `reporting`, and `storage` to maintain backward compatibility.

**Trade-offs:** Any code importing from `cli` pulls the entire CLI layer as a dependency. Adding a new domain function requires updating the re-export list. This is a known weakness tracked in ARCH-001.
