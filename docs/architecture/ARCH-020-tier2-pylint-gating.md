# ARCH-020: Promote Tier 2 pylint complexity rules to hard-fail

**Status:** done
**Priority:** medium
**Complexity:** medium

## Rationale

ARCH-019 enabled Tier 1 `pylint` across the whole project but left Tier 2
complexity rules (`R0912` too-many-branches, `R0913` too-many-arguments,
`R0914` too-many-locals, `R0915` too-many-statements, `R0902`
too-many-instance-attributes, `W0401` wildcard-import, `C0411`
wrong-import-order) as advisory via `|| true` in the `pylint-check` target.

Advisory rules decay in practice: the signal was reported but ignored, and
new violations accumulated (64 findings at the start of this task). This
task promotes Tier 2 to hard-fail so that `make verify` blocks further
complexity regression.

## Implementation

### Per-file refactors

Each finding was resolved by one of:

1. **Extract params dataclass** — group a cluster of related kwargs into a
   frozen dataclass (`EventContext`, `CostAuditContext`, `BootstrapPaths`,
   `BootstrapCallbacks`, `PracticeSourceRow`).
2. **Decompose long functions** — split monolithic functions into named
   helpers. Examples:
   - `reporting.print_summary` → `_print_{product_quality,operational,entries,history_signals}_block`.
   - `event_store.replay_events` → `_apply_{single_goal,goals_merged,usage_synced}_event`.
   - `history/normalize.normalize_codex_history` → `_build_normalize_indexes`,
     `_insert_normalized_{threads,usage_events,sessions,messages,logs,projects}`.
   - `history/ingest.ingest_codex_history` → `_snapshot_warehouse`,
     `_accumulate_snapshot_delta`, `_import_source_and_update_totals`.
   - `history/ingest._import_claude_session_file` → `_parse_claude_session_header`,
     `_insert_claude_session_and_thread`, `_ingest_claude_session_event` and
     related insert helpers.
   - `runtime_facade.sync_usage` / `cli.sync_usage` →
     `_resolve_sync_usage_window` + `_apply_auto_usage_updates`.
   - `runtime_facade.merge_tasks` → `_validate_merge_preconditions`,
     `_verify_merge_supersession`, `_merge_kept_task_fields`,
     `_rehome_entries_and_resolve_model`.
   - `commands.handle_history_update` → `_summarise_ingest_results`.
   - `commands.handle_render_html` → `_load_render_html_warehouse_rows`,
     `_render_html_source_message`, `_safe_load_effective_pricing`,
     `_resolve_render_html_cwd_and_warehouse`.
3. **Delegate duplicates** — `cli.merge_tasks` now delegates to the
   decomposed `runtime_facade.merge_tasks` rather than carrying a full copy.
4. **Dict-based dispatch** — `cli.main` replaced 26 `if args.command == "..."`
   branches with a `dict[str, handler]` dispatch, dropping the R0912/R0915
   that had started to grow.

### Per-file inline disables

Inline `# pylint: disable=...` suppressions are used on two categories of
construct where tier 2 thresholds make the code worse, not better:

**Canonical data schemas (R0902 too-many-instance-attributes).** Dataclasses
whose fields map 1:1 to an external contract — the ndjson goal schema, the
SQL warehouse rows, or a JSON report payload — cannot be compressed into
nested structs without breaking dict/row round-tripping or report output.
Affected dataclasses: `GoalRecord`, `AttemptEntryRecord`, `EffectiveGoalRecord`,
`RetroTimelineEvent`, `RetroMetricWindow`, `RetroWindowDelta`,
`HistoryCompareReport`, `IngestSummary`, `CostAuditCandidate`,
`ProductQualitySummary`, `BootstrapPlan`, `_IngestTotals`, `_WarehouseSnapshot`,
`_NormalizeIndexes`.

**CLI-contract boundary functions (R0913/R0914).** `apply_goal_updates`,
`upsert_task`, `resolve_goal_usage_updates`, and `build_attempt_entry` have
wide kwargs that mirror the `update` / `start-task` / `finish-task` argparse
flags and the `AttemptEntryRecord` schema. Grouping into sub-dataclasses is
tracked as a future task once the update-precedence rules stabilise.
`build_parser` similarly suppresses R0914/R0915 because argparse setup for
26 subparsers is inherently long and splitting it into per-command helpers
would trade one long function for 26 tiny ones without shared reuse.

`build_effective_goal_record` suppresses R0914 because its local count
mirrors the width of the `EffectiveGoalRecord` output contract.

### Gate wiring

The `pylint-check` target now runs tier 2 without `|| true`, and the
pyproject comment block reflects the promotion. `make verify-fast` and
`make verify` both fail if any suppressed rule appears without an explicit
inline disable.

## Acceptance Criteria

- [x] Tier 2 rules run against all modules with zero findings.
- [x] `make verify` fails on any new tier 2 violation.
- [x] Inline `# pylint: disable=...` suppressions are documented with the
      reason and scoped to the narrowest possible target.
- [x] The pyproject comment block distinguishes Tier 1 and Tier 2 without
      implying that Tier 2 is advisory.
- [x] The pylint-check target no longer uses `|| true` for Tier 2.
