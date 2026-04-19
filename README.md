# ai-agents-metrics

[![CI](https://github.com/sg4tech/ai-agents-metrics/actions/workflows/ci.yml/badge.svg)](https://github.com/sg4tech/ai-agents-metrics/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ai-agents-metrics)](https://pypi.org/project/ai-agents-metrics/)
[![Downloads](https://img.shields.io/pypi/dm/ai-agents-metrics)](https://pypi.org/project/ai-agents-metrics/)
[![License](https://img.shields.io/pypi/l/ai-agents-metrics)](https://github.com/sg4tech/ai-agents-metrics/blob/main/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/ai-agents-metrics)](https://pypi.org/project/ai-agents-metrics/)

**Analyze your AI agent work history. Track spending. Optimize your workflow.**

AI is writing more of your code. You still don't know:
- How many attempts each task actually takes
- Where the process breaks down and why
- Whether your workflow is getting faster or generating more rework

`ai-agents-metrics` extracts these signals from your existing Claude Code or Codex history — no manual setup required. Point it at your history files and see what's happening: retry pressure, token cost, session timeline. For richer tracking, add explicit goal boundaries and outcome labels on top.

---

## Why this exists

AI coding tools optimize for code generation. That is not the same as optimizing the development system around AI.

A coding agent can succeed at the individual task while the overall workflow degrades — more attempts per goal, more correction passes, more cost per shipped unit.

This project surfaces the signals that matter at the workflow level:
- how many attempts goals require,
- where retries and failures cluster,
- whether outcomes are matching the requested result,
- whether cost is trending in the right direction.

The key insight: these signals are already present in your agent history files. `ai-agents-metrics` extracts them. You do not need to set up manual tracking to get value — though you can add it for explicit goal classification and outcome labels.

It is not a benchmark, an eval framework, or a model comparison tool. It is a local analysis tool for real engineering work done with AI.

---

## What It Tracks

**From history files (no setup required):**
- **Retry pressure** — how often attempts fail or require correction, derived from session history
- **Token cost** — input, output, and cached-input tokens per session, mapped to USD
- **Model usage** — which model ran each session and what it cost
- **Session timeline** — full activity history from first ingest

**With optional manual tracking:**
- **Goals and attempts** — what was requested, how many passes it took, and whether each pass succeeded
- **Outcome quality** — result-fit labels for product goals (`exact_fit`, `partial_fit`, `miss`)
- **Failure reasons** — classified cause when an attempt does not succeed

---

## Findings from real data

Running this pipeline against a single developer's 6-month history (3.85B tokens, 160 threads, 334 sessions) surfaced several mechanisms that affect anyone analyzing Claude Code or Codex history — not just this dataset. Each finding is reproducible from raw history files:

| # | Finding | Headline |
|---|---------|----------|
| [F-001](docs/findings/F-001-claude-retries-are-subagents.md) | 100% of Claude "retries" are subagent spawns, not user retries | `0 / 160` threads have `main_attempt_count > 1` |
| [F-002](docs/findings/F-002-claude-user-role-is-not-human.md) | Claude's `role='user'` is mostly not human-typed | 86.7% of `role='user'` events are `tool_result` or template |
| [F-003](docs/findings/F-003-practice-split-is-size-confounded.md) | Naive practice-effectiveness split is size-confounded | 20× naive gap collapses to ~2.5× after size-matching; ~half is subagent overhead |
| [F-004](docs/findings/F-004-rework-signal-exists-but-n-too-small.md) | Cross-thread file-rework signal is detectable but N=66 too small for effectiveness claims | 61% of implementation threads have a rework follow-up within 30 days |
| [F-005](docs/findings/F-005-practice-distribution.md) | Discovery and commit-automation dominate real AI-coding practice usage | 29% of threads use any practice; discovery=39% of events, code_review=14% |

Full index: [docs/findings/README.md](docs/findings/README.md).

These are N=1 findings about the data, not universal claims. The mechanisms (subagent-aliased retries, `role='user'` pollution, size-confounded splits) are properties of the underlying tools — they will show up on anyone's history.

---

## Capabilities

| Capability | Status |
|---|---|
| History ingestion from Claude Code and Codex transcripts | Available |
| Structural session-kind classification (main vs subagent) | Available |
| Retry pressure derived from session history | Available |
| Cost and token tracking from history | Available |
| Automatic cost sync from Claude Code telemetry | Available |
| Automatic cost sync from Codex telemetry | Available |
| Before/after workflow comparison | Available |
| Interactive HTML report with trend charts | Available |
| Goal and attempt lifecycle CLI (opt-in manual tracking) | Available |
| Append-only local event log (NDJSON) | Available |
| Repository bootstrap (`bootstrap` command) | Available |
| Optional markdown report export | Available |
| Shell completion (bash, zsh) | Available |
| Standalone binary packaging | Available |
| Hosted multi-user dashboards | Not planned |
| Centralized team analytics | Not planned |

---

## Quick Start

```bash
pipx install ai-agents-metrics   # macOS / modern Linux (recommended)
# pip install ai-agents-metrics  # inside a virtualenv

# Run the full history pipeline (reads ~/.codex + ~/.claude by default):
ai-agents-metrics history-update
# Or restrict to a single source:
ai-agents-metrics history-update --source codex    # Codex only (~/.codex)
ai-agents-metrics history-update --source claude   # Claude Code only (~/.claude)

# See retry pressure, token cost, and session timeline
ai-agents-metrics show
```

That's it — no prior setup required. If you want to also add explicit goal tracking on top, see [Track a Session](#track-a-session).

---

## Example Output

```
$ ai-agents-metrics show

Codex Metrics Summary
Operational summary:
Closed goals:           17
Successes:              15
Fails:                  2
Success Rate:           88.24%
Known total cost (USD): 312.59
Known total tokens:     776,219,632
By model:
  claude-sonnet-4-6: 16 closed, 14 successes, 2 fails

History signals (warehouse):
  Project threads:           87  (worktrees merged)
  Threads with main_attempt > 1: 0 / 87 (structural retries)
  Subagent spawns:             156 sessions (Agent tool_use)
  Per-goal alignment:          16 / 17 ledger goals matched to history window
```

The `History signals` section is derived directly from session history files — no manual tracking required. The pipeline runs a deterministic filename-based classifier that separates *main attempts* (user-driven retries) from *subagent spawns* (internal delegation). A naive file-per-attempt count would conflate the two — see [F-001](docs/findings/F-001-claude-retries-are-subagents.md).

---

## Install

Install from PyPI:

```bash
pipx install ai-agents-metrics   # macOS / modern Linux (recommended)
pip install ai-agents-metrics    # inside a virtualenv
```

Install from source:

```bash
python -m pip install -e .
```

Install the standalone binary:

```bash
make package-standalone
./dist/standalone/ai-agents-metrics install-self
```

---

## Analyze History

Extract metrics from existing agent session files in one command:

```bash
ai-agents-metrics history-update                   # reads ~/.codex + ~/.claude (all sources)
ai-agents-metrics history-update --source codex    # restrict to Codex only
ai-agents-metrics history-update --source claude   # restrict to Claude Code only
```

Or run the three stages individually (ingest → normalize → derive):

```bash
ai-agents-metrics history-ingest
ai-agents-metrics history-normalize
ai-agents-metrics history-derive
```

Then inspect results:

```bash
ai-agents-metrics show
```

Compare the structured event log against reconstructed history to find gaps:

```bash
ai-agents-metrics history-compare
```

Analyze before/after product metrics around each retrospective event:

```bash
ai-agents-metrics derive-retro-timeline
```

---

## Inspect Metrics

Print a summary of retry pressure, costs, and session history:

```bash
ai-agents-metrics show
```

Explain missing cost coverage and check whether it is recoverable from local agent logs:

```bash
ai-agents-metrics audit-cost-coverage
```

Regenerate the optional markdown report (opt-in, requires manual tracking bootstrap):

```bash
ai-agents-metrics render-report
```

Generate a self-contained interactive HTML report with four trend charts (goal types, retry pressure, cost stacked by model, cost per success) and a summary strip showing total cost, success rate, and cost trend:

```bash
ai-agents-metrics render-html
ai-agents-metrics render-html --output report.html --days 30
```

The report reads token and retry data from the local warehouse when available (full history) and falls back to the event log. The output file has no external dependencies — open it in any browser.

---

## Bootstrap a Repository (opt-in)

To also enable manual goal tracking, run once to scaffold `ai-agents-metrics` into a repository. Creates the event log, installs the policy document, and injects an agent instructions block:

```bash
ai-agents-metrics bootstrap --target-dir /path/to/repo --dry-run
ai-agents-metrics bootstrap --target-dir /path/to/repo
```

Safe to rerun on a partially initialized repository. Use `--dry-run` to preview what will be written without making changes.

---

## Track a Session

History extraction gives you retry pressure, cost, and session timelines — but it cannot tell you *which specific tasks* had the worst outcomes or *why* a particular session failed. Manual goal tracking adds that layer: per-task breakdowns, outcome quality labels (`exact_fit`, `partial_fit`, `miss`), and classified failure reasons.

If your history shows 32% retry pressure, manual tracking tells you whether it's coming from unclear requirements, model mistakes, or scope problems — and on which tasks.

### Concepts

| Concept | Meaning |
|---|---|
| **goal** | One requested outcome |
| **attempt** | One implementation pass or retry for a goal |
| **outcome** | Final result: `success` or `fail` |
| **result fit** | Quality label: `exact_fit`, `partial_fit`, or `miss` — a goal can succeed but still be a partial fit |
| **failure reason** | Primary cause when an attempt fails: `model_mistake`, `unclear_task`, `validation_failed`, `environment_issue`, `scope_too_large`, `missing_context`, `tooling_issue`, `other` |

### Start a goal

Record a new goal before implementation begins:

```bash
ai-agents-metrics start-task --title "implement login endpoint" --task-type product
```

Goal types: `product` for delivery work, `retro` for retrospective writeups, `meta` for bookkeeping and tooling work.

### Record a correction pass

If the first attempt needed correction, record the retry:

```bash
ai-agents-metrics continue-task --task-id 2026-04-08-001 --failure-reason model_mistake
```

### Close the goal

When the goal is complete, close it with an outcome and optional quality label:

```bash
ai-agents-metrics finish-task --task-id 2026-04-08-001 --status success --result-fit exact_fit
ai-agents-metrics finish-task --task-id 2026-04-08-001 --status fail --failure-reason unclear_task
```

### Ensure bookkeeping is in place

If work has already started without an active goal, use this to detect and create a recovery draft:

```bash
ai-agents-metrics ensure-active-task
```

### Backfill cost data

Backfill token and cost data from local agent telemetry into existing goal records. Supports Claude Code and Codex automatically — no provider flag required:

```bash
ai-agents-metrics sync-usage
```

### Audit the ledger

Flag suspicious ledger patterns — likely misses, stale in-progress goals, and low cost coverage:

```bash
ai-agents-metrics history-audit
```

---

## Privacy and Storage

All data stays local. `ai-agents-metrics` writes only to:

- `.ai-agents-metrics/warehouse.db` — local SQLite warehouse used by the history pipeline
- `metrics/events.ndjson` — append-only event log for manual goal tracking (opt-in)
- `docs/ai-agents-metrics.md` — optional markdown export (regenerated on demand)

No data is sent to any remote service. The event log is a plain NDJSON file you can read, audit, and version-control yourself.

---

## Verify Your Install

```bash
make verify
```

Runs lint, security scan, typecheck, tests, and the public boundary check.

---

## Public Boundary

This repository contains the public-safe core only. Private retrospectives, internal audits, and local metrics history are kept in a separate private overlay. The boundary is enforced automatically:

```bash
make verify-public-boundary
```

---

## Repository

[github.com/sg4tech/ai-agents-metrics](https://github.com/sg4tech/ai-agents-metrics)

## Releasing

Publishing to PyPI is automated via GitHub Actions. To release a new version:

1. Merge all changes to `main` on this repository
2. Create and push a tag: `git tag v0.x.y && git push public v0.x.y`
3. The [publish workflow](https://github.com/sg4tech/ai-agents-metrics/actions/workflows/publish.yml) triggers automatically on the tag and publishes to PyPI via Trusted Publishing — no credentials required locally

Manual publishing with `twine` is not needed — the workflow handles it.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). In short: keep changes public-safe, run `make verify`, include tests for behavior changes.

## Security

See [SECURITY.md](SECURITY.md) for how to report potential private-data leaks or security issues.

## Changelog

Notable public changes are tracked in [CHANGELOG.md](CHANGELOG.md).
