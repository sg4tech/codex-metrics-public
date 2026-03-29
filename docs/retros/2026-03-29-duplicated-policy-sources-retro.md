# Duplicated Policy Sources Retrospective

## Situation

The repository ended up with two different codex-metrics policy texts:

- `docs/codex-metrics-policy.md`
- `src/codex_metrics/data/bootstrap_codex_metrics_policy.md`

They were both being treated as authoritative in different contexts.

The user correctly pointed out that this created avoidable ambiguity and made it unclear which policy a bootstrapped repository would actually receive.

## What Happened

We gradually improved the exported bootstrap policy so it was easier for a newly bootstrapped agent to understand.

Separately, we also continued improving the repository-facing policy in `docs/`.

Those two edits happened on parallel tracks, and nothing enforced that they stayed aligned.

By the time we checked them directly, they had drifted into materially different documents.

## Root Cause

The packaging and bootstrap design required a runtime-copyable policy file inside `src/`, but the repository also wanted a readable top-level policy in `docs/`.

That duplication was acceptable only if synchronization was explicit and enforced.

Instead, we had:

- two editable files
- no canonical source declaration
- no automated drift check

So divergence was eventually inevitable.

## Retrospective

This was not just a documentation mismatch. It was a product-surface mismatch.

The exported policy affects how other repositories are bootstrapped, while the repo policy affects how this repository is operated. If those differ, then the tool exports one contract while the source repo presents another.

That breaks trust quickly.

The important design constraint here is real:

- bootstrap must be able to read policy content from packaged runtime data
- so it cannot safely depend on `docs/` from the source checkout at install time

That means we cannot simply delete the packaged copy today.

But we also cannot leave two hand-maintained policy texts unconstrained.

## Conclusions

- Runtime bootstrap data belongs in `src/`, not in `docs/`.
- A repository-facing policy document can still exist in `docs/`, but it must be a synchronized mirror, not an independently evolving text.
- If two files must exist for packaging reasons, there still needs to be exactly one policy content.
- Drift between user-facing repo docs and exported bootstrap artifacts should be treated as a regression, not as a soft documentation issue.

## Permanent Changes

- Keep the bootstrap policy inside package data so installed packages and standalone binaries can export it reliably.
- Mirror the same content in `docs/codex-metrics-policy.md` for repository readability.
- Add an automated test that requires the packaged policy and the repo policy to match exactly.
- Treat future policy edits as touching both surfaces together unless and until the docs copy becomes generated from the packaged source.
