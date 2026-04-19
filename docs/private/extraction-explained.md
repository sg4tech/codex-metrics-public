# Extraction explained — plain-language walkthrough

**Last updated:** 2026-04-19
**Purpose:** Founder-facing explainer of how `ai-agents-metrics` turns raw `~/.codex` / `~/.claude` history files into the goals, attempts, and token numbers shown in reports. Grounded in a real run on partial local data (dump at `~/ai-agents-metrics-data/`, this machine only, Claude-source only — main data lives on a second machine).

---

## 1. The pipeline in three sentences

1. **Ingest** reads raw `.jsonl` conversation files from `~/.claude/projects/*` and `~/.codex/*` into a SQLite warehouse as-is (nothing decided, just copied into rows).
2. **Normalize** cleans and deduplicates those rows — trims timestamps, groups sessions, drops junk — without changing what they mean.
3. **Derive** applies two primitive rules to produce the numbers you see in reports: **one Claude/Codex thread = one goal**, **one session file within that thread = one attempt**. Nothing else. No semantics.

Everything downstream (cost, retry pressure, model dominance, project rollups) is arithmetic on top of those two rules.

---

## 2. What a "goal" actually is

A **goal** in the warehouse is literally a Claude/Codex **thread**. A thread is a UUID that Claude Code/Codex uses to group related sessions. When you run `claude` in the same repo, it tends to reuse the same thread UUID until something breaks that (new `--continue`, a restart, etc.). When the thread changes, the tool calls it a new goal.

An **attempt** is one `.jsonl` session file inside that thread, numbered 1..N by timestamp. `retry_count = attempts - 1`. That's the entire definition.

Both of these are **mechanical boundaries from Claude Code's own file structure**, not semantic ones. The tool has no idea what the user was trying to do. It sees only files.

Consequences:
- Opening `claude` in a second terminal while the first is running → usually a new thread → a new "goal", even if it's the same task.
- A single long thread where you worked on 4 different tasks → one "goal" with 4 attempts that look like retries.
- A skill/subagent call that spawns a short side-session → counted as an extra attempt against whatever thread it lives under.

This is the single biggest reason the goal/attempt numbers feel opaque. They are correct at the file-boundary level and often wrong at the intent level.

---

## 3. One worked example from real data

Thread `8f895086-8622-496a-9712-6375e3ce8d5b`, 2026-04-16. Warehouse reports this as **1 goal with 5 attempts**. What actually happened:

| Attempt | Model | Messages | Tokens | Duration | First→Last |
|---|---|---|---|---|---|
| 1 | `claude-opus-4-7` | 93 | **62.9M** | ~8h | 09:26:59 → 17:44:40 |
| 2 | `claude-haiku-4-5` | 8 | 1.0M | 38 sec | 09:27:38 → 09:28:16 |
| 3 | `claude-haiku-4-5` | 12 | 1.6M | 67 sec | 11:29:16 → 11:30:23 |
| 4 | `claude-haiku-4-5` | 7 | 0.6M | 30 sec | 11:43:36 → 11:44:06 |
| 5 | `claude-opus-4-7` | 2 | 0.2M | 59 sec | 17:31:06 → 17:32:05 |

Look at the timestamps: attempts 2, 3, 4 all start **inside the wallclock of attempt 1** (attempt 1 runs 09:26 → 17:44; attempt 2 starts 09:27). These are not retries — they are side-sessions (skill invocations, subagent calls, model-switch-for-a-single-question) that Claude Code stores as separate `.jsonl` files but that belong to the same user goal.

So the tool says "5 attempts, 4 retries". The honest reading is: **1 main Opus session, 3 Haiku side-calls, 1 short follow-up**. The "retry count" of 4 is structurally wrong for any effectiveness analysis on this thread.

This is the shape of bug the auto-classifier (revised H-015) is meant to fix — not by changing the warehouse rules, but by adding a semantic layer on top that says "attempt 2 is a skill call, not a retry."

---

## 4. Where tokens come from and what they mean

Each assistant response in a Claude session emits a `token_count` event with a `last_token_usage` dict. `history_normalize.py` pulls those into `normalized_usage_events`. `history_derive.py` sums them per session into `derived_session_usage`:

- `input_tokens` — fresh, never-cached input for this call
- `cache_creation_input_tokens` — tokens written into the prompt cache on this call
- `cached_input_tokens` — tokens served from the prompt cache (cheap)
- `output_tokens` — what the model generated
- `total_tokens` — sum of the above

On this machine's 5 days of data, **96% of all tokens are `cached_input_tokens`** (182M / 189M). That's the reason cost stays sane — the prompt cache is doing most of the work. Any cost analysis must treat cached input as a separate price tier, not roll it into generic "input".

**Cost itself is not in the warehouse.** No table has a `cost_usd` column. Cost is computed elsewhere (`usage_backends.py`) from a pricing table applied to these token counts, and is currently stored only in `metrics/events.ndjson` goal records. That means if pricing is stale or misses a model, there is no warehouse-level cross-check.

---

## 5. What the pipeline does NOT extract

Concrete list of holes:

| Field | Status | Why |
|---|---|---|
| Goal title | **Always NULL** | Claude stores an auto-summary in the first `.jsonl` event but ingest doesn't read it. Every goal in reports appears only as a UUID. Biggest UX hole. |
| `failure_reason` | **Always NULL in warehouse** | There is no column in any derived table. The field exists only on `GoalRecord` in `events.ndjson` and is populated only by a human running `finish-task fail`. Since the user refuses manual tagging (H-036 confirmed), this field is effectively dead until an LLM classifier writes it. |
| `result_fit` / outcome | **Always NULL in warehouse** | Same as above — only populated by manual workflow. |
| `reasoning_output_tokens` | **Always NULL** | Claude doesn't emit reasoning tokens. Expected, not a bug. |
| Intent / goal-type | Not extracted | The `product / meta / retro` taxonomy lives only in the manual ledger. The warehouse has no idea what each thread was for. |
| Cross-thread goal grouping | Not done | If the same task spans 3 new-chat threads, those are 3 separate goals. No stitching. |
| Practice markers (retro, QA-pass, code-review) | Not extracted | The central thesis (H-015) is that these should be auto-classified from message content. This does not exist yet. |

---

## 6. Known bugs and risks

Ordered by severity. Numbers below reference code paths in `src/ai_agents_metrics/history/`.

1. **`derive_insert.py:247–251` — project-stats `or 0` default.** Project-level aggregation does `stats_entry["input_tokens"] += sums.inp or 0`. If a session has `sums.inp is None`, it adds 0 silently. **Latent** on this dataset — the 2 sessions with NULL token totals have no usage events at all (legit), and totals match exactly when summed two different ways (verified: 189,514,614 via both paths). Bug fires only on sessions with *mixed* coverage (some usage events with None values alongside populated ones). Fix: either (a) skip None and track coverage explicitly, or (b) propagate None upward so the number is visibly absent rather than silently zeroed.

2. **Goal/attempt boundary is a file-boundary, not an intent boundary.** See section 3. This is the structural issue the practice classifier has to work around, not the pipeline itself.

3. **Multi-model sessions flattened to one dominant model.** `_dominant_model` (`derive_insert.py:184–198`) picks the most-frequent model per session with a lexicographic tiebreaker. A session mixing Opus+Haiku reports as a single model; cost slices based on "model of this session" will be off. On this user's workflow (Claude Code + Codex) this risk is elevated, but the current dump is Claude-only so not yet observable.

4. **No warehouse-level cost.** Tokens ≠ cost. The pipeline can be internally consistent on tokens while cost-per-goal is wrong, and there is no cross-check inside the warehouse. First cost audit needs to cross-reference `usage_backends.py` pricing against current Anthropic/OpenAI pricing.

5. **Message-to-usage attribution is greedy-nearest.** `_resolve_usage_for_message` (`derive_insert.py:97–104`) assigns each `usage_event` to the nearest assistant message by event index. For streaming responses or multi-turn reasoning, this can misattribute tokens. Matters for per-message cost; does not affect per-session or per-goal totals.

6. **Goal-title not populated from the first-message summary.** Easy to fix; high UX payoff.

---

## 7. Sanity check on current data

Run on this machine, Claude-source only, 2026-04-13 → 2026-04-18.

- 17 goals (threads), 29 attempts (sessions), 583 messages, 2,010 usage events
- 6 goals with `attempt_count > 1` (35% retry pressure)
- Model mix: haiku (10 sessions), sonnet (8), opus-4-6 (5), opus-4-7 (4)
- Total: 189.5M tokens (96% cached)
- `derived_projects.total_tokens == SUM(derived_session_usage.total_tokens)` — matches exactly. Arithmetic is internally consistent.
- 2/17 goals have `model=NULL` — correspond to sessions with zero usage events (minimal, legitimate)
- 17/17 goals have `title=NULL` (#1 UX issue)

This is **partial** data. Most development happens on a second machine. Before any practice-effectiveness claim lands, data from both machines has to be merged into one warehouse run.

---

## 7b. Retry pressure is structurally zero on warehouse-full (2026-04-19)

Descriptive practice-pass on `~/ai-agents-metrics-data/warehouse-full.sqlite` (160 threads total, Claude + Codex, 3.85B tokens) confirmed that `derived_goals.attempt_count > 1` is not driven by user retries at all.

| Dimension | Result |
|---|---|
| Claude threads with `main_sessions > 1` (filename = UUID, not `agent-*`) | **0 / 88** |
| Codex threads with `sessions > 1` (no subagent mechanism) | **0 / 72** |
| Warehouse-wide threads with `main_attempt_count > 1` | **0 / 160** |
| Claude threads with `subagent_sessions > 0` | 37 / 88 (one thread up to 17 subagents) |

All `attempt_count > 1` in `derived_goals` is Claude subagent spawning mis-counted as retries. On Codex the column is always 1.

**Analytical consequence:** "retry pressure" as an outcome variable has zero variance on current data and cannot be used to measure practice effectiveness. H-015 step 6 ("do retrospectives correlate with fewer retries?") is not a testable claim on this dataset. Any downstream analysis that treats `attempt_count` or `retry_count` as a retry proxy without the H-040 structural correction will produce noise; with the correction, the signal is still zero.

**Second confound flagged in the same pass:** thread-level splits "practice-present vs practice-absent" are dominated by task size. Threads with a `code-review:code-review` or `pr-review-toolkit:code-reviewer` event have 20× more total tokens and 22× longer duration than threads without. Discovery (`Explore` agent): 5× tokens, 17× duration. This is a size confound, not an efficiency signal. Any future practice-effectiveness analysis needs within-thread, matched-pair, or time-trend methodology — not naive split comparison.

---

## 8. How this feeds the central product thesis

The warehouse gives you **structure** (threads, sessions, tokens, timestamps, messages) but no **semantics** (what was this thread about? was this a retro? did the user ask for a QA pass?).

Revised H-015 (central thesis — `docs/private/product-hypotheses/H-015.md`) builds the semantic layer as an **auto-classifier over normalized messages** that emits practice-event rows: `(thread_id, session_path, practice_type, confidence)`. Practice types to start: `retrospective`, `qa_pass_requested`, `code_review_pass`, `discovery_before_implementation`.

That layer is only worth building once the base numbers (this document) are trustworthy and the known holes above are either fixed or explicitly scoped as "not used by analysis yet". Writing this doc *is* the first step of that gate.

---

## 9. Related reading

- `oss/docs/history-pipeline.md` — user-facing pipeline overview (lighter)
- `oss/docs/data-schema.md` — full field reference
- `docs/private/product-strategy.md` — 2026-04-18 amendment locks product direction
- `docs/private/product-hypotheses/H-015.md` — central thesis (practice-effectiveness via auto-classifier)
- `docs/private/product-hypotheses/ideas/H-036-zero-manual-tracking.md` — confirmed decision that all analysis must be derivable from history alone
