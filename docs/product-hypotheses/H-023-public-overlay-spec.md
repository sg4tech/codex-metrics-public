# Feature Spec: Public-First Core With Private Overlay

## Status

- Draft date: `2026-04-04`
- Owner: `product / repository strategy`
- Intended audience: `development team`
- Related hypothesis: [H-023](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-023.md)

## Problem

The current private repository mixes reusable product code with internal-only operational material.

Observed repository-local examples:

- `docs/retros/`
- `docs/audits/`
- `metrics/codex_metrics.json`
- local metrics/history state under ignored paths such as `metrics/.codex-metrics/`

This creates two conflicting needs:

1. publish the reusable code safely in a public repository
2. keep internal analysis, operating context, and local artifacts private

If the current repository is simply made public, tracked internal files and git history become disclosure risk.

If the current repository stays private and the public repo is treated as a hand-maintained export, outbound and inbound sync will likely become fragile, high-friction, and easy to get wrong.

## Goal

Create a repository model that supports all of the following at once:

- a clean public repository for reusable `codex-metrics` code
- a private repository for internal-only material
- low-friction outbound movement from private work into public code
- low-friction inbound movement from public contributions back into private work
- an explicit boundary that reduces accidental disclosure
- an automated verification path that blocks publication if private-only information leaks into the public repository

## Non-Goals

This plan should not:

- preserve the full existing private git history in the public repository
- make every current document public
- solve secret management through git mechanics alone
- require contributors to learn a complicated multi-repo workflow on day one
- optimize first for elegance over safety
- rely only on human review to catch private-data disclosure before public publication

## Product Intent

The repository topology should reinforce the product boundary:

- public repo = reusable product core
- private repo = internal operating overlay

The public-facing code and docs should become easier to consume and contribute to.

The private repository should remain the place for internal retrospectives, audits, local measurements, and operating instructions that are not meant for public distribution.

## Proposed Model

### Canonical Repositories

Use two repositories with distinct roles:

- `codex-metrics-public`
  - canonical source for reusable code, packaging, tests, public docs, examples, and public CI
- `codex-metrics-private`
  - canonical source for internal-only docs, audits, retros, local operational material, and any private overlays

### Recommended Sync Mechanism

Use `git subtree` as the first implementation candidate.

Why `subtree` is the leading option:

- keeps ordinary clones simple
- avoids `submodule` initialization and detached-reference friction
- supports real bidirectional sync
- makes the public slice explicit through one owned directory boundary

This spec does not require `subtree` forever, but the first validation should use it before considering more complex alternatives.

### Directory Boundary In The Private Repository

Keep the public code inside one dedicated subtree directory in the private repository.

Recommended path:

- `oss/`

Private repository target shape:

```text
codex-metrics-private/
  oss/                         # subtree mirror of the public repository
  docs/
    retros/
    audits/
    ...
  metrics/
    codex_metrics.json
    .codex-metrics/
  private-only scripts or notes if needed
```

Public repository target shape:

```text
codex-metrics-public/
  src/
  tests/
  tools/
  docs/                        # only the public-safe subset
  pyproject.toml
  README.md
  LICENSE
  .github/
```

## Public / Private Classification Rules

### Public-Eligible By Default

These should be considered public candidates unless a specific file contains sensitive content:

- `src/`
- `tests/`
- `tools/`
- packaging files such as `pyproject.toml`
- install and usage docs
- contributor docs
- public-facing CI and release workflows

### Private-Only By Default

These should stay private unless deliberately rewritten for publication:

- `docs/retros/`
- `docs/audits/` when they contain internal analysis or third-party project review notes
- local metrics ledgers and local history artifacts
- workspace-specific operational instructions
- environment-specific notes, local experiments, or private analysis snapshots

### Requires Explicit Review

These need manual classification instead of blanket inclusion or exclusion:

- `AGENTS.md`
- `docs/codex-metrics-policy.md`
- `docs/task-lifecycle.md`
- `docs/local-linear-setup.md`
- `docs/product-framing.md`
- `docs/product-hypotheses.md`

Reason:

- some of these contain valuable public product thinking
- some describe private operating process rather than public product usage
- some may need a public-safe rewrite instead of direct publication

## First-Pass Content Strategy

### Public Repository Should Initially Include

- library and CLI code
- tests
- packaging
- README and install flow
- a minimal public docs set sufficient for:
  - what the tool is
  - how to install it
  - how to run it
  - how to contribute

### Public Repository Should Initially Exclude

- retrospective archive
- internal audits
- local metrics source-of-truth history
- local snapshots from other repositories
- private workflow decisions that are only useful inside the current operating environment

### Public Docs Rewrite Rule

When a private document contains reusable insight but also internal context:

- do not publish it verbatim
- create a rewritten public version with internal details removed
- keep the original private version in the overlay repo

## Detailed Implementation Plan

### Phase 0: Boundary Audit

Objective:

- decide what is public-safe, private-only, or needs rewrite

Work:

1. inventory the current top-level directories and tracked docs
2. classify each path into:
   - `public`
   - `private`
   - `rewrite`
3. identify any files whose current location makes the boundary ambiguous
4. write the first allowlist for public export

Exit criteria:

- one reviewed classification table exists
- no high-risk directory is still “we will decide later”

### Phase 1: Create The Public Repository

Objective:

- stand up a clean public repository with only the reusable product core

Work:

1. create a new empty public repository
2. copy or extract only the allowlisted public content into it
3. add public-safe root docs:
   - `README.md`
   - `LICENSE`
   - `CONTRIBUTING.md` if ready
4. ensure `.gitignore` matches public needs
5. make CI pass in the public repository alone

Exit criteria:

- public repo clones and verifies independently
- no private-only files are present

### Phase 2: Restructure The Private Repository

Objective:

- turn the private repository into an internal overlay rather than a full parallel product repo

Work:

1. create an `oss/` directory in the private repo
2. import the public repository into `oss/` via `git subtree`
3. move private-only content outside `oss/`
4. update local scripts, docs, and habits so the team knows:
   - product code lives in `oss/`
   - internal material lives outside it
5. remove duplicate copies of public code from the private root once the subtree layout is stable

Exit criteria:

- private repo has a clean `oss/` boundary
- internal-only content remains accessible
- the same public code is no longer maintained in two separate places inside private

### Phase 3: Validate Outbound Sync

Objective:

- prove that a private-origin improvement can be published safely

Work:

1. make a small real code change under `private/oss/`
2. verify it locally
3. push that subtree change to the public repository
4. confirm the public repository remains clean and complete

Exit criteria:

- one real outbound sync completes without manual file picking

### Phase 4: Validate Inbound Sync

Objective:

- prove that a public-origin contribution can be brought back into private

Work:

1. merge one real or simulated contribution in the public repository
2. pull it back into `private/oss/`
3. confirm private-only files are untouched
4. confirm internal tooling still works against the updated subtree

Exit criteria:

- one real inbound sync completes cleanly

### Phase 5: Operationalize The Workflow

Objective:

- make the model sustainable instead of “it worked once”

Work:

1. document the daily rules:
   - public-worthy code changes go in `oss/`
   - private docs and analysis stay outside `oss/`
2. document sync commands
3. add guardrails where useful:
   - path-level checks
   - release checklist
   - public export verification
   - automated private-data leakage detection
4. decide whether some docs should have:
   - private canonical version
   - public rewritten version

Exit criteria:

- the team can explain the workflow in a few sentences
- sync no longer depends on memory or chat history
- the phase 1 public export helper can build a minimal tree and run the boundary verifier successfully

## Working Rules After Migration

### Rule 1: Public-Worthy Product Changes Start In `oss/`

If a change could reasonably belong in open source:

- implement it inside `oss/`
- verify it there
- publish outward from there

This prevents repeated extraction work later.

### Rule 2: Internal Analysis Never Lives In `oss/`

Retrospectives, audits, local snapshots, and internal operational notes should stay outside the public subtree.

### Rule 3: Rewrites Beat Redactions

If a document is partly useful and partly sensitive:

- write a public-safe version
- do not try to maintain one file with selective deletions before each sync

### Rule 4: One Boundary, Not Many Exceptions

Prefer a strong directory boundary over path-by-path special handling.

The more exceptions the split needs, the more likely the sync model is wrong.

## Suggested Sync Operations

These commands are intentionally illustrative rather than final automation.

### Import Public Into Private

```bash
git subtree add --prefix=oss <public-remote> main --squash
```

### Push Private `oss/` Changes To Public

```bash
git subtree push --prefix=oss <public-remote> main
```

### Pull Public Changes Back Into Private

```bash
git subtree pull --prefix=oss <public-remote> main --squash
```

The exact branch names can vary, but the operating principle should stay the same:

- `oss/` is the sync surface
- private-only material is never part of those subtree operations

## Required Leakage Guardrail

The repository model must include an explicit automated guard against publishing private information into the public repository.

This should not be treated as optional hygiene.

It is part of the core safety model.

### Required Verification Command

Add one dedicated verification command for the public repository boundary.

Suggested shape:

```bash
make verify-public-boundary
```

or, if the project prefers tool-level naming:

```bash
./tools/codex-metrics verify-public-boundary
```

The exact command name can be decided later, but the capability is mandatory.

### Required Integration

This boundary check should run automatically as part of the strongest normal local verification path.

For this repository, the intended default is:

```bash
make verify
```

That means:

- `make verify` should fail if the public repository contains private-only files
- `make verify` should fail if the public repository contains known private-content signatures
- no public-sync or release workflow should rely on memory alone to enforce the boundary

### Minimum Detection Scope

The first implementation should check at least these buckets:

- forbidden paths
  - examples: `docs/retros/`, `docs/audits/`, local metrics ledgers, snapshots, local history stores
- forbidden file patterns
  - examples: `.sqlite`, `.log`, private snapshot JSON, local lock files where relevant
- forbidden content markers
  - examples: internal-only headers, known private path prefixes, local workspace references, or other repository-specific disclosure markers discovered during the boundary audit

### Detection Model

Prefer an allowlist-oriented model over a vague blacklist-only model.

That means the guard should ideally combine:

1. allowed public roots
2. forbidden private roots
3. content-signature checks for files that are allowed structurally but may still contain private details

### Failure UX

When the verification fails, the output should be concrete and reviewable.

Minimum expectations:

- list the offending paths
- explain whether the failure is path-based or content-based
- fail loudly enough that public publication is blocked

### First-Pass Acceptance Criteria For The Guard

- a dedicated boundary-verification command exists
- `make verify` runs that command
- the command fails on a seeded forbidden path
- the command fails on a seeded forbidden content marker in an otherwise allowed file
- the command passes on a clean public repository

## Verification Plan

Minimum verification before calling the model validated:

1. public repository builds and tests independently
2. private repository still supports internal workflows after the split
3. one outbound private-to-public sync succeeds
4. one inbound public-to-private sync succeeds
5. no private-only path appears in the public repository
6. automated boundary verification catches seeded private-leak cases
7. the workflow can be followed without manual path selection

## Acceptance Criteria

- a new public repository exists and is usable on its own
- the private repository no longer depends on “sanitize before publish” as the main protection
- reusable product code has one clear home
- internal-only material has one clear home
- bidirectional sync has been tested in both directions
- boundary verification is automated and wired into normal verification
- the operating model is documented clearly enough for future work

## Main Risks

- the first chosen boundary may be wrong, especially for mixed docs
- moving the public code under `oss/` in private may require local script and path updates
- some contributors may accidentally edit the wrong repository or the wrong path during the transition
- public and private docs may drift if rewrite rules are not explicit
- a path-only guard may miss private information embedded inside otherwise public-safe files

## Guardrails

- keep the first public scope narrower than feels emotionally ideal
- prefer publishing less at first over exposing too much
- keep the sync boundary directory-based
- add content-level leakage checks, not only path-level checks
- test round-trip sync with real changes before declaring success
- document classification decisions while they are fresh

## Open Questions

- should `AGENTS.md` remain private, be rewritten publicly, or be split into public and private variants
- which parts of `docs/codex-metrics-policy.md` are true public product contract versus local operating policy
- whether the private repo should continue to run product tests from `oss/` directly or through wrappers
- whether public release automation should live only in the public repo after the split
- exact implementation details for boundary verification are specified in [H-023-public-boundary-verify-spec](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-023-public-boundary-verify-spec.md)
- whether the first public rollout should include generated SEO-oriented docs or landing pages, as captured separately in [H-024](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-024.md)

## Suggested Execution Order

1. classify repository contents
2. create the public repo with the smallest useful public scope
3. verify the public repo independently
4. import that repo into private as `oss/`
5. move internal-only content outside the subtree boundary
6. run one outbound sync
7. run one inbound sync
8. implement and wire boundary verification into `make verify`
9. only then codify stronger automation

Checkpoint:

- the first real public repo skeleton now exists at `/Users/viktor/PycharmProjects/codex-metrics-public` and was initialized from the phase 1 export
- the private repo now has an `oss/` overlay marker plus helper commands that print the planned `git subtree` sync flow, so the public/private split can be staged without immediately moving the whole codebase under `oss/`
