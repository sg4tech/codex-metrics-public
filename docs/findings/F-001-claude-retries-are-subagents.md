# F-001 — 100% of Claude "retries" are subagent spawns, not user retries

**Dataset:** `~/.claude` history of one developer, 88 Claude Code threads, 262 session files, ~6 months. Verified 2026-04-19 on `warehouse-full.sqlite`.

## TL;DR

If you count Claude Code `.jsonl` session files per thread, you get a number that looks like "retry count" — but 100% of it is subagent spawning, not the user retrying. On this dataset, **zero threads have more than one main session.**

## What "retry count" usually means

Most AI-usage dashboards (including an early version of this one) compute something like:

```
attempt_count = count of session files per thread
retry_count   = attempt_count - 1
```

Intuition: if a thread has 3 session files, the user probably restarted twice. This intuition is wrong for Claude Code.

## Why it's wrong

Claude Code stores each subagent invocation as a separate `.jsonl` file, named `agent-<uuid>.jsonl` (or `subagents/agent-acompact-<uuid>.jsonl` for compact subagents). These files are siblings of the main thread's `<uuid>.jsonl` file and share the same parent `thread_id`. A naive "file-per-attempt" counter treats every `Agent` tool_use — every time Claude internally delegates work to a subagent — as if the user had retried.

## Measurement

On this dataset:

| Dimension | Count |
|---|---|
| Claude sessions total | 262 |
| ↳ main sessions (UUID-named files) | 88 |
| ↳ subagent sessions (`agent-*.jsonl`) | 156 |
| ↳ compact subagent sessions (`subagents/agent-acompact-*`) | 18 |
| Claude threads with `main_sessions > 1` | **0 / 88** |
| Codex threads with `sessions > 1` (no subagent mechanism exists in Codex) | **0 / 72** |
| Warehouse-wide threads with `main_attempt_count > 1` | **0 / 160** |

Thread distribution by subagent count: 51 threads have 0 subagents, 15 have 1, rest trail off to a single outlier with 17 subagents.

## Reproducing

The rule that distinguishes main from subagent is purely filename-based and 100% deterministic on this dataset:

```python
def session_kind(session_path: str) -> str:
    base = os.path.basename(session_path)
    if base.startswith('agent-') or '/subagents/' in session_path:
        return 'subagent'
    return 'main'
```

No regex over payload, no LLM, no heuristics. Also cross-verified: on one sampled thread, every `Agent` tool_use event in the main session has a matching `agent-<uuid>.jsonl` file with timestamp within 3ms of the tool_use event.

## Implications

- **If you build a "retry pressure" metric over Claude data**, you are almost certainly measuring subagent-invocation intensity, not retry. Separate the two by filename before aggregating.
- **If you compare Claude and Codex** on the same dashboard, "retries" will always show higher on Claude for this structural reason alone.
- **If the outcome variable is "did the user retry"**, this variable has zero variance on N=1-developer Claude data. You need a different outcome.

## Caveats

- N=1 developer. Other developers may use Claude Code in ways that actually produce multiple main sessions per thread (e.g. heavy `--continue` usage after crashes).
- The filename convention is an internal Claude Code detail. A future release could change it; the classifier should degrade to `unknown` if filenames stop matching the known patterns.
- Codex's single-session-per-thread pattern may be specific to Codex's archival structure (`rollout-<timestamp>-<uuid>.jsonl`); other tools may differ.

## Related

- Data-model rules: [warehouse-layering.md](../warehouse-layering.md)
- Pipeline stages: [history-pipeline.md](../history-pipeline.md)
