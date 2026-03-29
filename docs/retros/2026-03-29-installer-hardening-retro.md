# Installer Hardening Retrospective

## Situation

After adding standalone binaries and improving shell UX, the next friction point moved one step later in the lifecycle:

- getting a stable `codex-metrics` command onto the machine
- keeping it updated
- making sure the installed command is actually reachable by name

At that point, telling users to manually create symlinks or remember shell-profile edits was still more operational work than a polished self-host tool should require.

## What Happened

The first hardening step introduced `install-self`, intended to create a stable user-local entrypoint such as `~/bin/codex-metrics`.

That was the right direction, but QA and real usage surfaced several hidden problems:

1. The command existed in source, but an older standalone binary did not include it yet.
This produced a confusing mismatch where the codebase claimed `install-self` existed, but `dist/standalone/codex-metrics` still rejected it until the standalone artifact was rebuilt.

2. A successful install was not enough if the target directory was not on `PATH`.
The command could install correctly and still leave the user with `command not found`.

3. Script/module installation needed a launcher, not just a raw path handoff.
The installer had to create a working entrypoint that preserved the right Python execution surface instead of assuming all invocation modes were equivalent.

4. One more UX step remained after installation.
Users still had to manually update `~/.zshrc` or `~/.bashrc` unless the installer could do it explicitly and safely.

The final hardening pass added:

- a working `install-self` command
- PATH warnings when the install target is not discoverable
- an opt-in `--write-shell-profile` flag
- regression tests for launcher creation, PATH warnings, profile writing, and idempotency
- rebuilt standalone artifacts to ensure the new command actually exists in the distributed binary

## Root Cause

The deeper mistake was treating installation as if it ended once a file existed at the target path.

In practice, installation had four distinct layers:

- the feature exists in source
- the released artifact actually contains the feature
- the installed entrypoint is executable and points at the intended runtime
- the shell can discover that entrypoint by command name

Missing any one of those still breaks the user experience, even if the earlier layers look correct.

## Retrospective

This was a good example of why installer work needs the same QA mindset as runtime features.

The surface looked small, but the real contract was broader:

- the command must be present in the built artifact
- the command must create a valid launcher
- the launcher must point at the right runtime
- the shell must be able to find it

The useful product decision here was not to silently edit shell profiles by default.

Instead, the installer now has:

- safe default behavior
- explicit warnings when PATH is wrong
- an opt-in flag for writing the shell profile

That keeps the flow automatable without making hidden changes on behalf of the user.

## Conclusions

- A source-only feature is not complete until the released standalone artifact is rebuilt and revalidated.
- Installer success must include discoverability, not just file placement.
- Self-host installers should distinguish safe defaults from opt-in convenience automation.
- PATH assumptions are a real part of CLI product design and need automated coverage.

## Permanent Changes

- Added `install-self` as a built-in installer command for a stable user-local entrypoint.
- Added PATH diagnostics when the install target directory is not currently discoverable.
- Added `--write-shell-profile` as an explicit opt-in way to append the PATH export to the detected shell profile.
- Added regression tests for launcher generation, PATH warnings, shell-profile updates, and idempotent profile writes.
- Rebuilt and revalidated the standalone binary after installer-surface changes so distributed artifacts match the documented command set.
