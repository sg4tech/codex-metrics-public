# Decision Log

Key architectural and design decisions — why things are the way they are.

Format: decision title, context, reasoning, known trade-offs. Add new entries as decisions are made or recalled.

---

## Append-only NDJSON event log, not a mutable JSON file

**Context:** the tool tracks metrics for AI agent tasks across parallel git worktrees. The data needs to be stored persistently without causing merge conflicts.

**Decision:** `metrics/events.ndjson` is the source of truth — an append-only NDJSON log where each CLI command adds one line. State is reconstructed at read time by replaying all events in file order, last-write-wins per `goal_id` / `entry_id`. The summary is always computed in-memory; it is never stored.

**Reasoning:**
- Append-only log eliminates git merge conflicts: parallel worktrees each append new lines, and `git merge` can automatically concatenate them without conflict
- No write-back of full state means no risk of one worktree overwriting another's data
- Human-readable and git-diffable — each line is a discrete command event
- Replay is deterministic and can be inspected independently of the live system

**Trade-offs:** read-time replay adds a small cost on every `load_metrics` call (acceptable for hundreds of goals). The `tasks` / `goals` legacy alias is normalised in-memory during replay, not persisted.

**Supersedes:** the earlier decision to use `metrics/codex_metrics.json` as a mutable JSON file (removed from git tracking; added to `.gitignore`).

---

## fcntl for cross-process locking, not threading.Lock

**Context:** multiple CLI invocations may run concurrently against the same `events.ndjson`.

**Decision:** `storage.metrics_mutation_lock` uses `fcntl.flock`.

**Reasoning:** the tool runs as short-lived CLI processes, not a long-lived server. Concurrent access comes from multiple processes, not threads within one process. `fcntl.flock` works across processes; `threading.Lock` does not.

**Trade-offs:** fcntl is POSIX-only (no Windows support). Acceptable because the tool targets macOS/Linux developer environments.

---

## History pipeline as a separate SQLite warehouse

**Context:** Codex agent stores session history in `~/.codex/state_5.sqlite` and `~/.codex/logs_1.sqlite`. The tool needs to derive goal history from this raw data.

**Decision:** a three-stage pipeline (ingest → normalize → derive) with an intermediate SQLite warehouse at `.codex-metrics/codex_raw_history.sqlite`, separate from the primary JSON store.

**Reasoning:**
- Raw source data is large and noisy; normalisation and derivation are expensive
- The warehouse acts as a cache — the pipeline can be re-run without re-reading the source
- Each stage has a single responsibility and can be tested independently
- Derived results can be compared against `codex_metrics.json` without mutating it

**Trade-offs:** inter-stage contracts exist only as SQLite column names, not Python types (tracked in ARCH-006).

---

## Timestamps stored as ISO strings in dataclasses

**Context:** `GoalRecord` and `AttemptEntryRecord` have `started_at` and `finished_at` fields.

**Decision:** stored as `str | None`, not `datetime | None`.

**Reasoning:** initial implementation chose the simplest representation that serialises directly to JSON without a custom encoder.

**Known downside:** parsing is scattered across the codebase; two parse functions exist (`parse_iso_datetime` and `parse_iso_datetime_flexible`) because input format is not normalised at the boundary. This is a known weakness tracked in ARCH-003.

---

## cli.py as a re-export facade

**Context:** early in the project, external scripts and tests imported symbols directly from `cli.py` before the module structure was stable.

**Decision:** `cli.py` re-exports ~50 symbols from `domain`, `reporting`, and `storage` to maintain backward compatibility.

**Known downside:** any code importing from `cli` pulls the entire CLI layer as a dependency. Adding a new domain function requires updating the re-export list. This is a known weakness tracked in ARCH-001.
