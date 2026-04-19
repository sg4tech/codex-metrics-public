# F-002 — Claude's `role='user'` is mostly not human-typed

**Dataset:** Same as F-001 — 88 Claude Code threads, 17,305 events with `role='user'`. Verified 2026-04-19 on `warehouse-full.sqlite`.

## TL;DR

In a naive analysis, `role='user'` looks like it contains what the human typed. In Claude Code history, **86.7% of `role='user'` events are not plausibly human input** — they are tool-result wrappers or skill-template injections written by Claude Code itself into the user slot.

## The slot is overloaded

Claude Code's JSONL format uses `role='user'` for at least three distinct things:

1. **Actual human-typed messages.** The original source of the role name.
2. **`tool_result` events.** When the assistant calls a tool, the tool's output is written back into the conversation as `role='user'` — not as a separate role. A single tool call produces one `role='user'` event.
3. **Template injections.** Skills, `<system-reminder>` blocks, and context-preambles are written into the user slot as if they came from the user.

This is a Claude Code design choice (not a bug) — the Anthropic API itself treats tool results as user messages. But it means text analysis that filters to `role='user'` picks up a lot of non-user content.

## Measurement

| Category | Count | Share |
|---|---|---|
| Total `role='user'` events | 17,305 | 100% |
| Contain `"type":"tool_result"` | 14,960 | **86.4%** |
| Contain `<system-reminder>` | 632 | 3.7% |
| Contain `<command-name>` (skill invocation) | 48 | 0.3% |
| Any template / tool_result marker | 15,009 | **86.7%** |
| Remaining candidate human-authored | 2,296 | **13.3%** |

Thread-level template fingerprint (on a narrower 48-thread slice): code-review skill template fires in 54% of threads, mark-done/QA-pass template in 54%, context-injection preamble in 40%.

**Codex does not have this problem.** Codex `role='user'` events on the same dataset are predominantly actual human input, because Codex's JSONL separates tool responses from user messages.

## Implications

- **Any content classifier that ingests Claude `role='user'` naively will produce noise.** Practice-classifier, retro-detection, intent-detection — all need a template/tool_result filter as step 0.
- **Volume metrics based on `role='user'` count** ("user messages per session") will be dominated by tool-result volume, i.e. by tool usage intensity, not by human engagement.
- **Cross-provider comparisons are asymmetric.** Codex `user_messages` and Claude `user_messages` do not mean the same thing. Normalize before comparing.
- **Template injections are a structural signal.** The same pollution that breaks naive text analysis is also a deterministic practice-type signal — `<command-name>code-review` fired means code-review was invoked. Use it as a feature, not just a filter.

## Reproducing

```python
# Conservative filter for "plausibly human input" on Claude:
def looks_human(raw_json: str) -> bool:
    if '"type":"tool_result"' in raw_json: return False
    if '<system-reminder>' in raw_json: return False
    if '<command-name>' in raw_json: return False
    return True
```

This is a lower-bound filter — some `<system-reminder>` blocks contain genuine user content after the reminder, and some skill templates contain parameters the user typed. A production filter should look for these edge cases. But the 13.3% result is a reasonable first-pass estimate of the human-authored share.

## Caveats

- N=1 developer. Other users may invoke skills less (lowering template share) or use tools less (lowering tool_result share). The 86.7% split is specific to this dataset.
- The markers listed are the ones observed on this dataset. Other installations may have different skill templates; a complete classifier needs a maintained template catalog.
- The `tool_result` share is dominated by `Bash`, `Read`, `Edit` — these are high-frequency tools. Lower tool-intensity workflows will show lower pollution.

## Related

- Structural rules for message classification: [warehouse-layering.md](../warehouse-layering.md) Layer 3
- Data schema: [data-schema.md](../data-schema.md)
