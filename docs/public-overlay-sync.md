# Public Overlay Sync Runbook

Operational guide for syncing between the private repository and the public `oss/` subtree.

## Layout

```
codex-metrics/          ← private repo (this repo)
  oss/                  ← git subtree mirror of codex-metrics-public
  docs/retros/          ← private, never synced
  docs/audits/          ← private, never synced
  metrics/              ← private, never synced

codex-metrics-public/   ← public repo (sibling directory)
  src/
  tests/
  tools/
  docs/                 ← public-safe subset only
```

`oss/` is the only sync surface. Everything outside it stays private.

## Check Status

```bash
make public-overlay-status
```

Shows planned sync commands and whether the `oss/` directory exists.

## Outbound: Private → Public

Push private changes from `oss/` into the public repository.

```bash
make public-overlay-push
```

This runs boundary verification first, then `git subtree push --prefix=oss public main`.
Fails loudly if the boundary check detects private content.

**When to use:** after landing a change in `oss/` that should be public.

## Inbound: Public → Private

Pull public changes (contributor patches, fixes committed directly to public) back into `oss/`.

```bash
make public-overlay-pull
```

This runs `git subtree pull --prefix=oss public main --squash`, then re-runs boundary verification.

**When to use:** after merging a PR or committing directly in the public repo.

## Conflict Resolution

Conflicts during `subtree pull` are usually in `Makefile`, `README.md`, or source files
where both sides changed independently. Resolve them by:

1. Keeping the private (HEAD) version for features not yet in public (security scan, etc.)
2. Accepting public changes for files only modified there
3. Staging resolved files: `git add <file>`
4. Committing: `git commit`
5. Then re-running `make public-overlay-push` to push the merged result

## Boundary Verification

```bash
make public-overlay-verify
```

Scans `oss/` against `oss/config/public-boundary-rules.toml`.
Checks for forbidden paths, file extensions, and content markers (private keys, local paths, tokens).
Also runs automatically as part of `make public-overlay-push` and `make public-overlay-pull`.

## Classification Rules

| Content | Location | Synced? |
|---------|----------|---------|
| `src/`, `tests/`, `tools/`, `config/public-boundary-rules.toml` | `oss/` | Yes |
| `docs/retros/`, `docs/audits/` | outside `oss/` | Never |
| `metrics/`, local history artifacts | outside `oss/` | Never |
| `AGENTS.md`, `docs/codex-metrics-policy.md` | outside `oss/` | Manual review required |

## Do Not

- Edit public repo files directly and then push without pulling back into `oss/`
  (causes divergence that requires manual conflict resolution on next pull)
- Run `git subtree push` without running boundary verification first
- Move `docs/retros/` or `metrics/` inside `oss/`
