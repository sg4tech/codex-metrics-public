# H-023 Current Repository Classification

Concrete first-pass classification for the current private repository before the public split.

This file turns the `public / private / rewrite` boundary into an explicit working artifact for implementation.

## Status

- Draft date: `2026-04-04`
- Related hypothesis: [H-023](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-023.md)
- Related plan: [H-023-public-overlay-spec](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-023-public-overlay-spec.md)

## Top-Level Classification

| Path | Classification | Notes |
| --- | --- | --- |
| `.github/` | `public` | public CI and workflow automation candidate |
| `.githooks/` | `rewrite` | likely useful, but should not be published verbatim before the public workflow is settled |
| `.gitignore` | `public` | public repo will need its own ignore policy |
| `AGENTS.md` | `rewrite` | contains local operating instructions and should split into public-safe and private-only guidance if needed |
| `Makefile` | `public` | public repo should keep a canonical verification entrypoint |
| `README.md` | `public` | primary public entrypoint |
| `config/` | `public` | intended home for public-boundary verification rules |
| `docs/` | `mixed` | needs subtree-level classification below |
| `metrics/` | `private` | contains local source-of-truth metrics and local runtime state |
| `pricing/` | `public` | pricing model data is product code/config |
| `pyproject.toml` | `public` | packaging metadata |
| `scripts/` | `public` | keep only scripts that support public packaging, validation, or development |
| `src/` | `public` | core product code |
| `tests/` | `public` | public verification and contribution surface |
| `tools/` | `public` | public command wrapper should remain usable |

## Docs Classification

| Path | Classification | Notes |
| --- | --- | --- |
| `docs/codex-metrics-policy.md` | `rewrite` | likely split into public workflow contract and private operating policy |
| `docs/history-pipeline.md` | `rewrite` | technically useful, but should be reviewed for internal framing and local-path leakage |
| `docs/local-linear-setup.md` | `private` | repository-local workflow configuration |
| `docs/product-framing.md` | `rewrite` | may have public value, but currently reflects internal framing |
| `docs/product-hypotheses.md` | `rewrite` | some hypotheses may become public roadmap, but not all should be published unchanged |
| `docs/task-lifecycle.md` | `rewrite` | internal workflow details should be separated from any public contribution lifecycle |
| `docs/TODO.md` | `private` | internal working backlog |
| `docs/audits/` | `private` | internal analysis, including third-party project reviews and snapshots |
| `docs/experiments/` | `rewrite` | potentially reusable, but should be reviewed case by case |
| `docs/notes/` | `private` | internal notes |
| `docs/pilots/` | `private` | internal transition planning |
| `docs/product-hypotheses/` | `rewrite` | selected public-facing strategy docs may be publishable later |
| `docs/retros/` | `private` | explicit internal retrospective archive |

## Immediate Public Allowlist Candidates

These are the safest initial public candidates for the first repository split:

- `.github/`
- `.gitignore`
- `Makefile`
- `README.md`
- `config/`
- `pricing/`
- `pyproject.toml`
- `scripts/`
- `src/`
- `tests/`
- `tools/`

## Immediate Private-Only Paths

These should be excluded from the first public repository without further debate:

- `docs/retros/`
- `docs/audits/`
- `docs/notes/`
- `docs/pilots/`
- `docs/local-linear-setup.md`
- `docs/TODO.md`
- `metrics/`

## Immediate Rewrite Queue

These should not block the first public split, but they should not be published verbatim:

- `AGENTS.md`
- `docs/codex-metrics-policy.md`
- `docs/history-pipeline.md`
- `docs/product-framing.md`
- `docs/product-hypotheses.md`
- `docs/product-hypotheses/`
- `docs/task-lifecycle.md`
- `docs/experiments/`
- `.githooks/`

## Notes

- `2026-04-04`: this classification is intentionally conservative; publishing less at first is safer than trying to maximize the first public surface.
- `2026-04-04`: the boundary verifier should use this file as the human review companion, while the machine-enforced rules live in repo config.
