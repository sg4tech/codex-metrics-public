# ai-agents-metrics

[![CI](https://github.com/sg4tech/ai-agents-metrics/actions/workflows/ci.yml/badge.svg)](https://github.com/sg4tech/ai-agents-metrics/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ai-agents-metrics)](https://pypi.org/project/ai-agents-metrics/)
[![License](https://img.shields.io/pypi/l/ai-agents-metrics)](https://github.com/sg4tech/ai-agents-metrics/blob/main/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/ai-agents-metrics)](https://pypi.org/project/ai-agents-metrics/)

**Measure whether AI-assisted development is working.**

AI is writing more of your code. You still don't know:
- How many attempts each task actually takes
- Where the process breaks down and why
- Whether your workflow is getting faster or generating more rework

`ai-agents-metrics` tracks goals, attempts, outcomes, and token cost for every AI coding session — structured data to reason about your workflow, not just your model.

---

## Why this exists

AI coding tools optimize for code generation. That is not the same as optimizing the development system around AI.

A coding agent can succeed at the individual task while the overall workflow degrades — more attempts per goal, more correction passes, more cost per shipped unit.

This project tracks the signals that matter at the workflow level:
- how many attempts goals require,
- where retries and failures cluster,
- whether outcomes are matching the requested result,
- whether cost is trending in the right direction.

It is not a benchmark, an eval framework, or a model comparison tool. It is a local ledger for real engineering work done with AI.

---

## Core Concepts

| Concept | Meaning |
|---|---|
| **goal** | One requested outcome. Stored in the event log; `task` is a legacy alias used in CLI flags. |
| **attempt** | One implementation pass or retry for a goal. Multiple attempts per goal are normal when corrections are needed. |
| **session** | One continuous AI agent interaction (e.g. a single Claude Code or Codex thread). Maps to one or more attempts. |
| **outcome** | The final result of a closed goal: `success` or `fail`. |
| **failure reason** | The primary cause when an attempt does not succeed: `model_mistake`, `unclear_task`, `validation_failed`, `environment_issue`, `scope_too_large`, `missing_context`, `tooling_issue`, or `other`. |
| **cost** | Token spend mapped to USD for a goal or attempt. Sourced from local agent telemetry when available. |
| **retry pressure** | How many passes a goal required before closure. High retry pressure signals friction in the task or the workflow. |
| **result fit** | Quality label for closed product goals: `exact_fit`, `partial_fit`, or `miss`. Separate from outcome — a goal can succeed but still be a partial fit. |

---

## What It Tracks

- **Goals and attempts** — what was requested, how many passes it took, and whether each pass succeeded
- **Token cost** — input, output, and cached-input tokens per session, mapped to USD
- **Retry pressure** — how often attempts fail or require correction
- **Model usage** — which model ran each session and what it cost
- **Outcome quality** — result-fit labels for product goals
- **History analysis** — reconstruct past sessions from agent conversation transcripts

---

## Capabilities

| Capability | Status |
|---|---|
| Append-only local event log (NDJSON) | Available |
| Goal and attempt lifecycle CLI | Available |
| Retry and failure visibility | Available |
| Cost and token tracking | Available |
| Automatic cost sync from Claude Code telemetry | Available |
| Automatic cost sync from Codex telemetry | Available |
| History ingestion from agent transcripts | Available |
| Before/after workflow comparison | Available |
| Shell completion (bash, zsh) | Available |
| Standalone binary packaging | Available |
| Repository bootstrap (`bootstrap` command) | Available |
| Optional markdown report export | Available |
| Hosted multi-user dashboards | Not planned |
| Centralized team analytics | Not planned |

---

## Quick Start

```bash
pip install ai-agents-metrics

# Bootstrap tracking into a repository
ai-agents-metrics bootstrap --target-dir /path/to/repo

# Start a goal, do the work, close it
ai-agents-metrics start-task --title "add login endpoint" --task-type product
ai-agents-metrics finish-task --task-id 2026-04-09-001 --status success --result-fit exact_fit

# See what it cost and how many tries it took
ai-agents-metrics show
```

---

## Example Output

```
$ ai-agents-metrics show

Codex Metrics Summary

Operational summary:
Closed goals:                    8
Successes:                       8
Fails:                           0
Total attempts:                  8
Success Rate:                    100.00%
Attempts per Closed Goal:        1.00

Known total cost (USD):          9.27
Known total tokens:              26,337,605
  input:                         260
  cached:                        26,088,225
  output:                        44,883

Known Cost per Success (USD):    1.32
Known Cost per Success (Tokens): 3,762,515

Model coverage: 7/8 closed goals with an unambiguous model
By model:
  claude-sonnet-4-6: 7 closed, 7 successes, 0 fails

Closed entries:     8
Entry successes:    8
Entry fails:        0
Entry Success Rate: 100.00%
```

---

## Install

Install from PyPI:

```bash
pip install ai-agents-metrics
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

## Bootstrap a Repository

Run once to scaffold `ai-agents-metrics` into any repository. Creates the event log, installs the policy document, and injects an agent instructions block:

```bash
ai-agents-metrics bootstrap --target-dir /path/to/repo --dry-run
ai-agents-metrics bootstrap --target-dir /path/to/repo
```

Safe to rerun on a partially initialized repository. Use `--dry-run` to preview what will be written without making changes.

---

## Track a Session

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

---

## Inspect Metrics

Print a summary of all goals, costs, and retry pressure:

```bash
ai-agents-metrics show
```

Audit goal history for likely misses, stale in-progress goals, and low cost coverage:

```bash
ai-agents-metrics history-audit
```

Explain missing cost coverage and check whether it is recoverable from local agent logs:

```bash
ai-agents-metrics audit-cost-coverage
```

Regenerate the optional markdown report:

```bash
ai-agents-metrics render-report
```

---

## Sync Cost Data

Backfill token and cost data from local agent telemetry into existing goal records. Supports Claude Code and Codex automatically — no provider flag required:

```bash
ai-agents-metrics sync-usage
```

---

## Analyze History

Reconstruct session history from local agent transcripts. Run the three pipeline stages in order:

```bash
ai-agents-metrics history-ingest
ai-agents-metrics history-normalize
ai-agents-metrics history-derive
```

For Claude Code sessions, add `--source claude`:

```bash
ai-agents-metrics history-ingest --source claude
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

## Privacy and Storage

All data stays local. `ai-agents-metrics` writes only to:

- `metrics/events.ndjson` — the append-only event log (source of truth)
- `docs/ai-agents-metrics.md` — an optional markdown export (regenerated on demand)
- `.ai-agents-metrics/warehouse.db` — a local SQLite cache used by the history pipeline

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

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). In short: keep changes public-safe, run `make verify`, include tests for behavior changes.

## Security

See [SECURITY.md](SECURITY.md) for how to report potential private-data leaks or security issues.

## Changelog

Notable public changes are tracked in [CHANGELOG.md](CHANGELOG.md).
