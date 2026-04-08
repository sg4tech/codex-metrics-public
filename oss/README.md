# codex-metrics

Open-source core for tracking AI-agent-assisted engineering work.

This repository is the public surface of `codex-metrics`. It contains the
shareable core, public-safe checks, and the guardrails that keep private data
out of the open-source tree.

## Quick Start

```bash
python -m pip install -e .
make setup-hooks
make verify
```

## What This Repo Is For

- Tracking Codex task metrics and derived reports.
- Keeping the public boundary explicit and testable.
- Providing a clean base for community contributions.

## What It Is Not For

- Private retrospectives, internal audits, or local logs.
- Secrets, tokens, personal paths, or workspace-specific state.
- Experimental internal tooling that is not safe to publish.

## Common Commands

- `make verify` runs lint, security, typecheck, tests, and the public boundary check.
- `make verify-public-boundary` scans the checkout for private-only content.
- `make setup-hooks` enables the local pre-commit boundary hook.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before sending patches. In short:

- keep changes public-safe
- run `make verify`
- include tests for behavior changes
- prefer small, reviewable pull requests

## Security

If you find a potential leak of private information or a security issue, read
[SECURITY.md](SECURITY.md) before reporting it.

## Releases

Release notes and notable public changes are tracked in [CHANGELOG.md](CHANGELOG.md).
