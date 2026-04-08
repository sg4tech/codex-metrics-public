# codex-metrics

**Track AI-agent task metrics: token cost, retry pressure, and outcome quality.**

`codex-metrics` is an open-source tool for measuring the real cost and effectiveness of AI-assisted engineering work. It records goals, attempts, token spend, and retry patterns so you can see which workflows are productive and which are burning tokens on rework.

## Why

AI coding agents (Claude Code, Codex, and similar) generate real costs and vary widely in effectiveness. Without measurement, it is hard to know whether a workflow is improving or whether a particular approach is worth the token spend. `codex-metrics` gives you a lightweight, local ledger for that data.

## What It Tracks

- **Goals and attempts** — what you asked the agent to do, how many tries it took
- **Token cost** — input, output, and cached-input tokens per session, mapped to USD
- **Retry pressure** — how often attempts fail or require correction
- **Model usage** — which model ran each session and what it cost
- **History analysis** — parse conversation transcripts to reconstruct past sessions

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

Open a goal:

```bash
codex-metrics open "implement login endpoint"
```

Close it when done:

```bash
codex-metrics close --outcome fit
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

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). In short: keep changes public-safe, run `make verify`, include tests for behavior changes.

## Security

See [SECURITY.md](SECURITY.md) for how to report potential private-data leaks or security issues.

## Changelog

Notable public changes are tracked in [CHANGELOG.md](CHANGELOG.md).
