# Contributing to codex-metrics

Thanks for helping improve `codex-metrics`.

## Before You Start

- Read the README and make sure your change belongs in the public repo.
- Run `make verify` before opening a pull request.
- Keep the public boundary clean. The repository must remain safe to publish.

## What We Accept

- Bug fixes.
- Small, well-scoped features.
- Documentation improvements.
- Test coverage improvements.

## What We Avoid

- Private-only material.
- Workspace-specific paths, logs, and local state.
- Broad refactors without a clear public benefit.

## Suggested Workflow

1. Create a small branch.
2. Make the change.
3. Run `make verify`.
4. Update or add tests if behavior changes.
5. Open a pull request with a short explanation of what changed and why.

## Public Boundary Rules

- Do not add private notes, retros, or internal audit data.
- Do not commit secrets, tokens, or local machine paths.
- If a change might expose internal context, treat it as private and keep it out
  of this repo.

## Commit Messages

Use short, descriptive commit messages. Keep them focused on one change.
