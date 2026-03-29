# 2026-03-29 Usage Recovery Format Mismatch Retro

## Situation

`codex-metrics` already had:

- automatic local usage recovery
- known vs complete cost coverage reporting
- `audit-cost-coverage`

But product cost coverage still looked weak, and the first audit output suggested:

- `no_usage_data_found`

for most closed product goals.

At first glance, that looked like a workflow or telemetry-retention problem.

## What Happened

We investigated the real local telemetry sources instead of trusting the first high-level interpretation.

That investigation showed:

1. The repository threads for `codex-metrics` did exist in `~/.codex/state_5.sqlite`.
2. Those threads also had many log rows in `~/.codex/logs_1.sqlite`.
3. The log rows included `response.completed` and token-bearing traces.
4. The session rollout JSONL files under `~/.codex/sessions/...` contained timestamped `token_count` events with `last_token_usage`.
5. The existing extractor only understood one legacy SQLite log pattern:
   - `event.name="codex.sse_event"`
   - `event.kind=response.completed`
   - `conversation.id=...`
   - `input_token_count=...`

So the data was not actually missing.

The extractor was simply too format-specific and was ignoring the newer telemetry path.

We then added a session-based fallback recovery path and re-ran `sync-codex-usage`.

Coverage changed dramatically:

- before: `4/92` known cost coverage
- after fallback + sync: `78/93` known cost coverage

That proved the root problem was not missing telemetry but a format mismatch between the current local Codex telemetry and our recovery logic.

## Root Cause

The recovery layer treated one legacy local telemetry representation as if it were the canonical local source.

That assumption became false once real local Codex usage for this repo started appearing through:

- newer thread-bound logs
- rollout session JSONL files with `token_count` events

The system therefore misclassified recoverable usage as missing usage.

## 5 Whys

1. Why did most product goals show `no_usage_data_found`?
   Because `resolve_codex_usage_window()` failed to recover usage for those goal windows.

2. Why did `resolve_codex_usage_window()` fail?
   Because it only searched for a narrow legacy SQLite log pattern and returned `None` when that pattern was absent.

3. Why was that pattern absent for this repository?
   Because the current local Codex telemetry for `codex-metrics` was being recorded in a different shape:
   - rollout session JSONL `token_count` events
   - newer thread-bound trace rows

4. Why did we initially think the usage data itself was missing?
   Because the first audit layer reported only the symptom (`no_usage_data_found`), not whether the failure came from:
   - absent telemetry
   - thread mismatch
   - extractor incompatibility

5. Why did the system not catch the format mismatch earlier?
   Because our verification had strong synthetic coverage and summary reporting, but no live E2E check against current real local telemetry artifacts.

## Theory Of Constraints

At first, the apparent constraint looked like:

- insufficient telemetry retention or cost capture

After investigation, the real constraint was:

- the recovery extractor was bound to an outdated local telemetry format

So the bottleneck was not:

- metrics math
- reporting semantics
- goal windows
- cost presentation

The bottleneck was:

- telemetry compatibility at the recovery boundary

Once that was fixed, cost coverage rose sharply without changing the product workflow itself.

## Retrospective

This was a strong example of why top-line audit categories are not enough on their own.

`no_usage_data_found` was directionally useful, but it was not specific enough to identify the real failure mode.

The real lesson is that:

- absence of recovered data is not the same as absence of source data

We only found the real issue once we inspected:

- state DB
- logs DB
- session rollout files
- actual thread IDs
- actual event formats

The investigation also validated an important engineering principle:

- preserve the old recovery path and add a fallback first, instead of rewriting the whole usage system

That kept the change small, reversible, and easy to validate.

## Conclusions

- local Codex usage data for this repo was present and recoverable
- the existing extractor was too tied to one legacy log format
- the correct fix was additive compatibility, not a reporting rewrite
- a live E2E smoke check was necessary to verify recovery against real telemetry
- cost audit categories need to be interpreted as hypotheses until the underlying telemetry source is inspected

## Permanent Changes

- keep the legacy SQLite SSE recovery path, but treat it as one supported source rather than the only source
- keep the rollout session fallback for `token_count` recovery
- keep `audit-cost-coverage`, but interpret `no_usage_data_found` as a diagnosis candidate, not final truth
- maintain an opt-in live smoke check against real local telemetry:
  - `make live-usage-smoke`
- when local recovery appears empty, inspect actual telemetry sources before concluding the data does not exist
