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

![HTML report preview — 5 charts over 25 goals, 243 practice events, 16 days](docs/images/report-preview.png)

> **Running this on 6 months of Claude Code + Codex history (3.85B tokens, 160 threads) surfaced:**
>
> - **100% of Claude "retries" are subagent spawns, not user retries** — `attempt_count > 1` is structural, not a failure signal ([F-001](docs/findings/F-001-claude-retries-are-subagents.md))
> - **Subagent delegation halves main-session tokens within-thread** — median 2.05× compression, p = 0.000456 ([F-007](docs/findings/F-007-practice-within-thread-compression.md))
> - **Per-skill compression ranking** — `Explore` 2.63×, `code-reviewer` 3.25×, `commit` 0.72× ([F-008](docs/findings/F-008-per-skill-compression-ranking.md))
>
> Full index: [docs/findings/](docs/findings/README.md). N=1 developer; the mechanisms generalize because they come from the tools, not the data.

---

## Quick start

```bash
pipx install ai-agents-metrics

ai-agents-metrics history-update     # reads ~/.codex + ~/.claude by default
ai-agents-metrics show               # retry pressure, cost, session timeline
ai-agents-metrics render-html        # interactive HTML report
```

Non-default history paths, full command list, and manual goal tracking (optional): [CLI reference](docs/cli-reference.md).

---

## What you get

- **History extraction** — retry pressure, token cost, model usage from existing session files. No setup.
- **HTML report** — one self-contained file, summary strip + 5 trend charts, opens in any browser.
- **Optional manual tracking** — add goal boundaries and outcome labels on top of history for per-task breakdowns.

Not a benchmark, not an eval framework, not a model comparison tool. It is a local analysis tool for real engineering work done with AI.

---

## Privacy

All data stays local. Writes only to:

- `.ai-agents-metrics/warehouse.db` — local SQLite warehouse used by the history pipeline
- `metrics/events.ndjson` — append-only event log for manual goal tracking (opt-in)
- `docs/ai-agents-metrics.md` — optional markdown export (regenerated on demand)

No data is sent to any remote service.

---

## Links

- [Repository](https://github.com/sg4tech/ai-agents-metrics) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)
- [CLI reference](docs/cli-reference.md) · [Findings](docs/findings/README.md) · [Architecture](docs/architecture.md)
