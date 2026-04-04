# Public-First Overlay Rollout Retro

## Situation

We wanted to open-source `codex-metrics` without exposing internal retrospectives, audits, local metrics state, or other private-only material.
The repository initially mixed reusable product code with internal operating artifacts, so a direct public flip would have been risky.

## What Happened

We introduced a public-first model with a private overlay:

- created a standalone public repo
- imported it into the private repo under `oss/` with `git subtree`
- added a boundary verifier that fails on private paths, forbidden globs, and private-content markers
- wired the verifier into the public repo hook and CI
- expanded the public surface in small, reviewable slices

The rollout went further than the initial split and ended up standardizing the public CLI around JSON output for the main read-only/reporting commands.

## Root Cause

The original structure did not clearly separate public-safe code from internal analysis and operational material.
That meant every sync decision had to be made by memory or review instead of by directory boundary and automation.

The deeper issue was not just repository layout.
It was the lack of an explicit, enforced contract for what could leave the private repo.

## Retrospective

The split worked because we treated the public boundary as a product constraint, not as a cleanup task.
That made it natural to build guardrails first and then add public slices incrementally.

The best part of the rollout was the combination of:

- small slices
- a dedicated `oss/` boundary
- `verify-public-boundary`
- pre-commit and CI enforcement

That gave us safe momentum without relying on manual memory.

## Conclusions

1. Public/open-source work needs a hard boundary, not a soft convention.
2. The boundary verifier should stay part of the normal verification path.
3. `git subtree` is a workable sync mechanism for this repo because it keeps the public slice explicit.
4. Read-only public commands benefit from machine-readable JSON output, which makes the repo more scriptable for both humans and agents.

## Permanent Changes

- Keep public-worthy code in `oss/` in the private repo.
- Keep internal retros, audits, and private notes outside `oss/`.
- Require `verify-public-boundary` before public syncs and in public CI.
- Prefer small, public-safe slices over broad extraction passes.
- Keep the public repo agent-friendly with JSON output on report/snapshot commands.

