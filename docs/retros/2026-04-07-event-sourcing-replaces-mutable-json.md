# Retro: Event Sourcing Replaces Mutable JSON Storage

**Date:** 2026-04-07
**Task:** CODEX-50
**Outcome:** success

---

## Situation

`metrics/codex_metrics.json` was a mutable, git-tracked file protected by an OS-level immutability flag (`chflags uchg`). Every CLI mutation rewrote the entire file. In a multi-worktree setup this caused two compounding problems:

1. The `uchg` flag on the file blocked `git pull` / `git merge` — git could not overwrite the file even with clean diffs.
2. When two worktrees diverged and both mutated the file, merging produced JSON content conflicts that git could not auto-resolve.

The problem was diagnosed in H-030 and tracked as CODEX-50.

---

## What Happened

### Design phase

Five design questions were clarified upfront before writing any code:

1. **Event schema** — chose command-level events (1:1 with CLI commands), full goal state in each payload, last-write-wins replay per `goal_id`/`entry_id`. Rejected per-field delta events (more complex replay) and periodic snapshots (same conflict problem).
2. **`codex_metrics.json` fate** — removed from git tracking, added to `.gitignore`. Not replaced by any persistent artifact.
3. **Immutability flag on `events.ndjson`** — explicitly rejected. An append-only log does not need a mutation guard; the flag would recreate the same git problem on the new file.
4. **Validation layers** — structural validation at append time; full business-rule validation after replay.
5. **Test infrastructure** — `test_storage_immutability.py` deleted, `conftest.py` uchg fixture removed, all inject-corrupt-data tests rewritten to write NDJSON events.

### Implementation

Core implementation was straightforward. Two non-obvious issues required investigation:

**Issue 1 — `goals_merged` and downstream supersession links.** After `merge_tasks`, goals whose `supersedes_goal_id` pointed to the dropped goal were rewritten to point to the kept goal. The initial `goals_merged` event only stored the kept goal. Replay left downstream goals stale (pointing to the deleted `goal_id`). Fix: snapshot all goals before merge, diff after, include changed downstream goals in the `goals` field of the `goals_merged` event. Replay handler applies them.

**Issue 2 — inject-corrupt-data tests.** Five tests wrote raw JSON directly to the metrics file to inject invalid state, then expected `show` to fail. After the change, the file is NDJSON events — a raw JSON dict has no `event_type` field and is silently skipped during replay, so the tests passed when they should have failed. Each test was rewritten to write a proper event containing the invalid data.

### CI failure

After the first push, CI failed on `test_packaged_policy_template_matches_repo_policy`. There is a packaged copy of the policy at `src/codex_metrics/data/bootstrap_codex_metrics_policy.md` that must stay in sync with `docs/codex-metrics-policy.md`. The policy was updated but the mirror was not. Fixed by copying.

### /simplify pass

Post-implementation review found three genuine issues:

- Three `recompute_summary()` calls immediately after `load_metrics()` in read-only handlers — redundant since `load_metrics` already calls it internally.
- Four inline `[e for e in data["entries"] if e.get("goal_id") == ...]` list comprehensions — `get_goal_entries()` already existed in domain and was exported.
- One hardcoded `Path("metrics/events.ndjson")` literal in `LOW_SIGNAL_WORKTREE_PATHS` duplicating the `EVENTS_NDJSON_PATH` constant defined two lines above.

All three fixed.

---

## Root Cause

The original design treated `codex_metrics.json` as a single-writer database — safe when one agent runs at a time. The multi-worktree workflow created concurrent writers, which neither the JSON format nor the immutability guard was designed to handle. The root cause is not a bug but an architectural mismatch between the storage model and the actual usage pattern.

**5 Whys:**

1. CI broke on merge → JSON content conflict in `codex_metrics.json`
2. Why conflict? → Two worktrees both mutated the full file independently
3. Why full file? → `save_metrics` always rewrote the entire JSON object
4. Why full rewrite? → State was stored as a single mutable document, not as an event log
5. Why mutable document? → Initial design assumed single-agent sequential access; multi-worktree was not a design constraint at the time

**Theory of Constraints:** The bottleneck was the storage model, not the merge tooling or the immutability guard. Removing the guard without changing the model would have kept the JSON conflict problem. Switching to append-only log eliminated the conflict class entirely.

---

## Retrospective

The design phase was well-structured. Clarifying five explicit decisions upfront prevented mid-implementation pivots. The two implementation issues (downstream supersession links, inject-corrupt-data tests) were found by the test suite rather than in production.

The packaged policy mirror miss was a known risk class: whenever a doc is mirrored in two places, both must be updated together. The test caught it in CI.

The `/simplify` review caught real issues — particularly the four `get_goal_entries` duplications. The utility existed and was exported; it was simply not imported in `commands.py`.

---

## Conclusions

- Append-only event logs are the right storage primitive for multi-writer CLI tools tracked in git.
- When two things must stay in sync, a test enforcing equality is the correct guardrail (not manual process).
- Inject-corrupt-data tests that write raw format bytes are fragile when the storage format changes — they need to be format-aware.
- Snapshot-based tests (`read_json(path)`) should be replaced by semantic helpers (`read_metrics(repo)`) when the storage format changes.

---

## Permanent Changes

| Change | Scope |
|--------|-------|
| Append-only NDJSON event store | Code (landed in CODEX-50) |
| `get_goal_entries` imported in `commands.py` | Code (landed in simplify pass) |
| Packaged policy mirror test (`test_packaged_policy_template_matches_repo_policy`) | Already existed — caught the miss |
| All docs updated (architecture, decisions, glossary, testing-guide, data-schema, AGENTS.md, policy) | Docs (landed in CODEX-50) |
| Note: when adding inject-corrupt-data tests, write events not raw JSON | `docs/testing-guide.md` — add note |
