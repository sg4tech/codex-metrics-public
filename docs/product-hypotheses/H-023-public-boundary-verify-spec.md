# Feature Spec: Public Boundary Verification

## Status

- Draft date: `2026-04-04`
- Owner: `product / repository safety`
- Intended audience: `development team`
- Related hypothesis: [H-023](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-023.md)
- Related plan: [H-023-public-overlay-spec](/Users/viktor/PycharmProjects/codex-metrics/docs/product-hypotheses/H-023-public-overlay-spec.md)

## Problem

After the repository split, safety will depend on one critical invariant:

- the public repository must not contain private-only information

That invariant cannot rely on memory, manual review, or “we usually remember not to copy that folder”.

The main failure modes are:

1. a clearly private file lands in the public repository
2. an allowed public file contains private content copied from internal notes or local environment data
3. a future refactor changes paths or docs structure and silently weakens the boundary

## Goal

Define an automated verification system that blocks public publication when the public repository contains private-only material or private-content markers.

This verification must be:

- explicit
- repeatable
- reviewable
- easy to run locally
- included in the normal strongest verification path

## Non-Goals

This feature should not:

- attempt generic secret scanning for every possible secret class
- replace human review entirely
- depend on the private repository being available at runtime
- infer policy from git history or chat transcripts
- silently auto-delete offending files

## Product Intent

The check exists to make accidental disclosure hard.

It is not a cosmetic lint.

It is a release-blocking safety guard for the public boundary.

## Required Command Surface

The first implementation should expose one dedicated verification command.

Preferred forms:

```bash
make verify-public-boundary
```

and/or:

```bash
python -m codex_metrics.verify_public_boundary
```

or:

```bash
./tools/codex-metrics verify-public-boundary
```

The exact entrypoint can be chosen by implementation convenience, but the behavior must be identical whichever wrapper is used.

## Required Integration

The check must run as part of the repository's strongest standard local verification path.

For this repository, the default requirement is:

```bash
make verify
```

That means:

- `make verify` must fail if boundary verification fails
- CI for the public repository should also run the same check
- any future public release workflow should call the same verification rather than a weaker duplicate

## Current Implementation Notes

The initial implementation has already landed with the following shape:

- a dedicated `verify-public-boundary` command is available
- the command is wired into `make verify`
- the public repository CI runs the same boundary check
- the verifier supports allowlisted roots, forbidden paths/globs/extensions, and content markers
- the pre-commit hook in the public repo uses the same boundary check
- a separate lightweight `security` command now scans staged changes for private-key and token-style leakage before commit
- the pre-commit hook in the private repo now invokes that `security` command before Ruff, so dangerous data is blocked early in the local workflow
- the pre-commit and commit-msg hooks resolve the repository root with `git rev-parse --show-toplevel`, so linked worktrees target the active worktree instead of the hook script's physical location
- log-like runtime outputs are ignored at the git level so they are less likely to be staged in the first place

The remaining work is mostly operational hardening and public polish:

- keep the allowlist current as the public surface grows
- add or refine fixtures whenever a new leak pattern is discovered
- keep boundary rules and docs synchronized between private `oss/` and the public repo
- make sure future workflow changes do not weaken the public boundary by accident
- extend the `security` command with additional OWASP Top 10-oriented checks as the surface area grows, and keep the same fast path available in both public and private repos

## Verification Target

The verifier runs against the public repository working tree.

First implementation assumption:

- the verifier is executed from the root of the public repository

It must inspect tracked files and, where relevant, untracked files that are not ignored and would plausibly be committed.

It does not need to inspect:

- ignored build artifacts
- `.git/`
- virtualenvs
- dependency directories

## Core Detection Model

The verifier should use layered checks.

It must not be only a path blacklist.

### Layer 1: Forbidden Path Rules

Fail if any path in the public repository matches a forbidden root or forbidden pattern.

Examples that should be representable:

- `docs/retros/**`
- `docs/audits/**`
- `metrics/**`
- `.codex-metrics/**`
- `**/*.sqlite`
- `**/*.log`
- `**/*.lock` when the lock file is not part of a deliberate public workflow
- snapshot directories or exported internal analysis artifacts

Purpose:

- catch obvious structural leakage fast

### Layer 2: Public Allowlist Rules

Define the expected public roots explicitly.

Examples:

- `src/**`
- `tests/**`
- `tools/**`
- `docs/**`
- `.github/**`
- `pyproject.toml`
- `README.md`
- `LICENSE`
- `Makefile`

This layer should answer:

- is this file even supposed to exist in the public repository

Recommended model:

- default-deny for top-level roots
- explicit allowlist for known public surfaces

Reason:

- allowlist drift is safer than accidental expansion

### Layer 3: Forbidden Content Markers

Even an allowed file should fail if it contains content that strongly suggests private origin.

The first implementation should support configurable literal markers and regex markers.

Examples of marker categories:

- internal-only headings
  - example: `Internal only`
  - example: `Do not publish`
- repository-specific private path references
  - example: `/Users/viktor/PycharmProjects/`
  - example: `docs/retros/`
  - example: `docs/audits/`
- local environment references
  - example: `~/.codex`
  - example: `.codex-metrics/`
- references to private workflow state
  - example: local Linear setup details if those are intentionally private
  - example: internal snapshots from other projects

Purpose:

- catch copied fragments that path rules alone cannot see

### Layer 4: Optional File-Type Rules

The verifier may apply stricter checks by file type.

Useful first-pass examples:

- markdown files: scan full text for forbidden markers
- JSON files: fail on private snapshot naming patterns or forbidden keys if needed
- binary-like files: fail by extension unless explicitly allowed

This layer is optional for the first pass if Layers 1 to 3 already provide strong coverage.

## Configuration Model

The rules should live in one explicit config file in the public repository.

Suggested location:

- `config/public-boundary-rules.toml`

Suggested config sections:

- `allowed_roots`
- `forbidden_paths`
- `forbidden_globs`
- `forbidden_extensions`
- `forbidden_literal_markers`
- `forbidden_regex_markers`
- `ignored_paths`

Why config instead of hardcoding only:

- boundary policy needs reviewable data
- docs structure may evolve
- tests can use fixture configs

## Suggested Rule Semantics

### Allowed Roots

Meaning:

- top-level roots or files that are legitimate in the public repo

Behavior:

- any top-level path outside these roots fails unless explicitly ignored

### Forbidden Paths And Globs

Meaning:

- any match is an immediate failure

Behavior:

- path match alone is enough to fail, even if the file content looks harmless

### Forbidden Extensions

Meaning:

- file types that should never appear publicly unless explicitly allowlisted

Examples:

- `.sqlite`
- `.db`
- `.log`
- maybe `.lock` depending on public tooling policy

### Forbidden Literal Markers

Meaning:

- exact string snippets that indicate likely private leakage

Behavior:

- simple substring check
- case-sensitive by default unless configured otherwise

### Forbidden Regex Markers

Meaning:

- patterns for variable content such as local absolute paths or structured private references

Examples:

- `/Users/[^/]+/PycharmProjects/`
- `docs/retros/[0-9]{4}-[0-9]{2}-[0-9]{2}-`

Behavior:

- regex match is a failure

### Ignored Paths

Meaning:

- files or directories excluded from scanning because they are generated, external, or irrelevant

This should be narrow.

The ignore list must not be used to bypass real boundary problems.

## Scan Scope

The verifier should inspect:

- all tracked files in the current working tree
- optionally untracked, non-ignored files under allowed roots

Why include untracked files:

- a contributor may stage or commit them next
- local pre-commit verification should catch likely mistakes early

The verifier should skip:

- ignored files
- directories explicitly ignored by config
- known dependency or virtualenv trees

## Output Requirements

On failure, the command must produce structured, human-readable findings.

Minimum output per finding:

- finding type
  - `forbidden_path`
  - `unexpected_root`
  - `forbidden_extension`
  - `forbidden_marker`
- file path
- short explanation
- marker or rule that matched, when relevant
- line number for text-content findings when practical

The command should end with:

- non-zero exit code on any finding
- zero exit code only when all checks pass

## Failure Examples

The verifier should fail in cases like:

1. `docs/retros/2026-04-04-retro.md` exists in the public repo
2. `docs/guide.md` contains a copied path like `/Users/viktor/PycharmProjects/codex-metrics`
3. `docs/overview.md` references `docs/audits/2026-04-03-history-audit-follow-up.md`
4. `metrics/codex_metrics.json` appears in the public repo
5. `docs/reference.md` contains an internal-only heading or marker from the rule set

## Pass Examples

The verifier should pass in cases like:

1. only allowlisted roots are present
2. public docs mention open-source contribution flow but do not reference internal directories
3. generated public-safe docs are present under allowed paths and contain no private markers

## Suggested Implementation Shape

The first implementation can be a small Python module.

Suggested internal components:

- `load_boundary_rules(path) -> BoundaryRules`
- `collect_candidate_files(repo_root, rules) -> list[Path]`
- `check_allowed_roots(files, rules) -> list[Finding]`
- `check_forbidden_paths(files, rules) -> list[Finding]`
- `check_forbidden_extensions(files, rules) -> list[Finding]`
- `check_forbidden_markers(files, rules) -> list[Finding]`
- `render_findings(findings) -> str`
- `main() -> int`

Suggested finding fields:

- `kind`
- `path`
- `message`
- `matched_rule`
- `line`

## Testing Requirements

The verifier should have automated tests from the first implementation.

Minimum test buckets:

### Happy Path

- clean public fixture passes

### Forbidden Path Rejection

- seeded `docs/retros/...` file fails
- seeded `metrics/...` file fails

### Unexpected Root Rejection

- unexpected top-level directory fails

### Forbidden Marker Rejection

- allowed markdown file containing a private absolute path fails
- allowed markdown file containing a forbidden private directory reference fails

### Ignore Handling

- ignored temp or build file does not trigger a false positive

### Output Shape

- failing run includes path and matched rule in output

## Acceptance Criteria

- one dedicated public-boundary verification command exists
- the rule set is stored in a reviewable config file
- forbidden path leakage is detected
- forbidden content leakage inside allowed files is detected
- unexpected roots are detected
- findings are reported with enough detail to fix them quickly
- the command is wired into `make verify`
- the public repository CI runs the same check

## Risks

- too many broad markers may cause noisy false positives
- too few markers may create false confidence
- docs rewrites may need regular rule maintenance as public wording evolves
- binary or generated files may need special-case handling

## Guardrails

- start with a narrow public scope
- keep the rule set explicit and reviewed
- prefer a few high-signal markers over a giant fuzzy list
- add regression tests when a new leakage pattern is discovered
- do not let ignore rules become a bypass for uncomfortable findings

## Open Questions

- whether `AGENTS.md` or parts of it will ever exist publicly
- whether public policy docs should have their own marker set distinct from code/docs generally
- whether the command should scan staged-only files in addition to the working tree
- whether the verifier should support a `--strict-untracked` mode

## Suggested Execution Order

1. define the first public boundary rule set
2. implement the verifier as a standalone command
3. add fixture-based tests for pass and fail cases
4. wire the command into `make verify`
5. run seeded leakage checks to prove the guard works
6. refine markers only after observing real false positives or misses
7. confirm that the minimal phase 1 export tree passes the verifier
