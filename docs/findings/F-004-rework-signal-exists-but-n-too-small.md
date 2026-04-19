# F-004 — Cross-thread file-rework signal exists, but N=66 is too small for effectiveness claims

**Dataset:** 66 Claude Code threads with ≥1 `Edit` / `Write` / `MultiEdit` event, 2026-04-19 measurement on `warehouse-full.sqlite`.

## TL;DR

Following [F-003](F-003-practice-split-is-size-confounded.md) — which ruled out naive practice-effectiveness split — we tested a more robust outcome variable: *does a thread's edit to file X come back as a follow-up edit to X in a later thread within 30 days?* The signal is real (61% of implementation threads have a rework follow-up) and measurable without retry variance. But at N=66 threads, practice-effectiveness differences are within noise — we cannot distinguish "code-review reduces rework by 13%" from "no effect."

## Setup

An *implementation thread* is a Claude thread with ≥1 `Edit`, `Write`, or `MultiEdit` tool_use (66 of 88 Claude threads, 75%). For each such thread we extract the set of file paths touched. A *rework chain* exists between threads A and B if A and B touched ≥1 common file and B started 1h–30d after A.

## Result — signal exists

| Dimension | Count |
|---|---|
| Implementation threads | 66 |
| Distinct files touched | 408 |
| Files touched by ≥2 threads | **76 (18.6%)** |
| Thread-pairs sharing ≥1 file | 308 |
| Rework chains (gap 1h–30d) | 292 |
| Implementation threads with ≥1 rework follow-up | **40 (61%)** |
| Median gap (days) between original and rework | 3.0 |
| Median shared files per pair | 1 |

61% of implementation threads have a downstream thread that re-edited the same file within a month. This is enough variance to be an outcome variable, AND it does not depend on retry structural signal (which is zero on this dataset per F-001).

## Result — practice-effect is within noise

Applying the same practice-splits as F-003, but to rework_rate (reworked_files / files_touched):

| Split | Any-rework | rework_rate mean | Interpretation |
|---|---|---|---|
| code_review WITH (n=18) | 56% | 0.281 | 6pp lower, 13% relative reduction |
| code_review WITHOUT (n=48) | 62% | 0.323 | baseline |
| discovery WITH (n=15) | 67% | 0.352 | **higher** than without |
| discovery WITHOUT (n=51) | 59% | 0.300 | baseline |

- **code_review** shows a small favorable effect (6pp lower any-rework rate, 13% lower mean rate). At N=18 vs N=48 and this effect size, a proper confidence interval would span zero — this could be noise.
- **discovery** (Explore) shows *higher* rework — 67% vs 59%. This is almost certainly the task-size confound from F-003 resurfacing: Explore fires on complex tasks, complex tasks have more files, more files = more chances one of them gets re-touched. The rework-rate normalization (rework per file touched) partially corrects for this but not fully at small N.

Honest interpretation: **practice-effect is not distinguishable from noise at this sample size.** Both directions are compatible with the data.

## What this means for ambitions

- **The rework methodology is valid.** Cross-thread file-overlap is a real, measurable, structurally-available outcome variable. Not every AI-metrics tool has one.
- **The sample size is not.** To detect a 13% rework-rate difference with reasonable confidence, power analysis suggests 3–5× more implementation-thread samples — i.e. months of additional data, not a methodology change.
- **Practice-effectiveness is not a near-term shippable claim.** On N=66 from one developer, the rework methodology says "can't tell." Publishing anything stronger would overclaim.
- **But the rework signal itself is a shippable product feature.** "Here are the files in your codebase that came back to edit most often" is a useful descriptive report independent of any effectiveness claim.

## Caveats and known confounds

- **File-touch is a weak rework proxy.** Re-editing a file doesn't always mean the earlier work was wrong — it may be unrelated feature work on the same file. A stronger proxy would check for line-overlap or functional-undo, which requires content-diff analysis not yet built.
- **Config files distort.** A single thread that touched `pyproject.toml` or CI config will appear in many rework chains for mundane reasons. Filtering by file-type (source only) would sharpen the signal.
- **30-day window is arbitrary.** Shortening to 7 days reduces chain count but may be more causally credible. Not tested.
- **Cross-project rework is conflated with intra-project iteration.** Two threads in the same repo editing the same file is legitimate rework. Two threads in different projects editing `README.md` is not. Stratifying by `cwd` would help.

## Related

- Precursor null result: [F-003](F-003-practice-split-is-size-confounded.md)
- Subagent-aliasing context (why retry was not usable): [F-001](F-001-claude-retries-are-subagents.md)
