# codex-metrics — track AI agent token cost and retry pressure

[![CI](https://github.com/sg4tech/codex-metrics-public/actions/workflows/ci.yml/badge.svg)](https://github.com/sg4tech/codex-metrics-public/actions/workflows/ci.yml)

**Measure the real cost and effectiveness of AI-assisted engineering work.**

`codex-metrics` is a local CLI tool that records goals, attempts, token spend, and retry patterns for every AI coding session — so you can see which workflows are productive and which are burning tokens on rework.

## Why

AI coding agents (Claude Code, Codex, and similar) generate real costs and vary widely in effectiveness. Common questions without this tool:

- *"How much did my Claude Code session cost?"*
- *"How do I track AI agent retries across tasks?"*
- *"What is my token spend per task?"*
- *"Did this workflow change actually improve anything?"*
- *"Which model is more cost-effective for my work?"*

`codex-metrics` gives you a lightweight, local ledger to answer all of these from real data.

## When to use this

- You use Claude Code, Codex, or another AI coding agent and want to know what each task actually cost
- You suspect certain types of tasks require too many correction passes and want the numbers to confirm it
- You changed a prompt strategy or workflow and want to verify it improved outcome quality or reduced cost
- You run AI agents as part of a paid engineering workflow and need to track whether AI cost is eating into project margins
- You want an AI agent to analyze your workflow history and recommend what to change next

## What It Tracks

- **Goals and attempts** — what you asked the agent to do, how many tries it took
- **Token cost** — input, output, and cached-input tokens per session, mapped to USD
- **Retry pressure** — how often attempts fail or require correction
- **Model usage** — which model ran each session and what it cost
- **History analysis** — parse conversation transcripts to reconstruct past sessions

## Example output

```
$ codex-metrics show

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

## Install

```bash
python -m pip install -e .
```

Or install the standalone binary:

```bash
make package-standalone
./dist/standalone/codex-metrics install-self
```

## Quick Start

Bootstrap a project:

```bash
codex-metrics bootstrap
```

Start tracking a goal:

```bash
codex-metrics start-task --title "implement login endpoint" --task-type product
```

Record another attempt if the agent needed a correction:

```bash
codex-metrics continue-task --task-id 2026-04-08-001 --failure-reason wrong_scope
```

Close it when done:

```bash
codex-metrics finish-task --task-id 2026-04-08-001 --outcome success --result-fit exact_fit
```

Show current metrics:

```bash
codex-metrics show
```

## Verify Your Install

```bash
make verify
```

Runs lint, security scan, typecheck, tests, and the public boundary check.

## Public Boundary

This repository contains the public-safe core only. Private retrospectives, internal audits, and local metrics history are kept in a separate private overlay. The boundary is enforced automatically:

```bash
make verify-public-boundary
```

## Repository

[github.com/sg4tech/codex-metrics-public](https://github.com/sg4tech/codex-metrics-public)

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). In short: keep changes public-safe, run `make verify`, include tests for behavior changes.

## Security

See [SECURITY.md](SECURITY.md) for how to report potential private-data leaks or security issues.

## Changelog

Notable public changes are tracked in [CHANGELOG.md](CHANGELOG.md).
