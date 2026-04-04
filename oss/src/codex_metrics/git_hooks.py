from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

ZERO_OID = "0" * 40

DOCS_ONLY_EXACT_PATHS = {
    "AGENTS.md",
    "README.md",
}
DOCS_ONLY_PREFIXES = (
    "docs/",
    "metrics/",
)


@dataclass(frozen=True)
class VerifyDecision:
    should_run: bool
    reason: str


def normalize_repo_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_docs_only_path(path: str) -> bool:
    normalized = normalize_repo_path(path)
    if not normalized:
        return True
    if normalized in DOCS_ONLY_EXACT_PATHS:
        return True
    return normalized.startswith(DOCS_ONLY_PREFIXES)


def decide_verify_for_paths(paths: Iterable[str]) -> VerifyDecision:
    normalized_paths = [normalize_repo_path(path) for path in paths if normalize_repo_path(path)]
    if not normalized_paths:
        return VerifyDecision(should_run=False, reason="no file changes detected in push range")

    code_paths = [path for path in normalized_paths if not is_docs_only_path(path)]
    if not code_paths:
        return VerifyDecision(should_run=False, reason="docs-only changes detected; skipping make verify")

    preview = ", ".join(code_paths[:5])
    if len(code_paths) > 5:
        preview += ", ..."
    return VerifyDecision(
        should_run=True,
        reason=f"code-affecting changes detected; running make verify ({preview})",
    )


class GitHookRunner:
    def git_lines(self, args: Sequence[str]) -> list[str]:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def changed_paths_for_ref_update(self, local_sha: str, remote_sha: str) -> list[str]:
        if not local_sha or local_sha == ZERO_OID:
            return []
        if remote_sha and remote_sha != ZERO_OID:
            return self.git_lines(["diff", "--name-only", f"{remote_sha}..{local_sha}"])

        commit_ids = self.git_lines(["rev-list", local_sha, "--not", "--remotes"])
        if not commit_ids:
            return self.git_lines(["diff-tree", "--no-commit-id", "--name-only", "-r", local_sha])

        changed_paths: list[str] = []
        seen_paths: set[str] = set()
        for commit_id in reversed(commit_ids):
            for path in self.git_lines(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_id]):
                normalized = normalize_repo_path(path)
                if normalized and normalized not in seen_paths:
                    seen_paths.add(normalized)
                    changed_paths.append(normalized)
        return changed_paths

    def run_verify(self) -> int:
        result = subprocess.run(["make", "verify"], check=False)
        return result.returncode


def run_pre_push(stdin: Iterable[str], runner: GitHookRunner | None = None) -> int:
    hook_runner = runner or GitHookRunner()
    changed_paths: list[str] = []
    seen_paths: set[str] = set()

    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        local_ref, local_sha, remote_ref, remote_sha = line.split()
        del local_ref, remote_ref
        for path in hook_runner.changed_paths_for_ref_update(local_sha, remote_sha):
            normalized = normalize_repo_path(path)
            if normalized and normalized not in seen_paths:
                seen_paths.add(normalized)
                changed_paths.append(normalized)

    decision = decide_verify_for_paths(changed_paths)
    print(f"pre-push: {decision.reason}")
    if not decision.should_run:
        return 0
    return hook_runner.run_verify()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git hook helpers for codex-metrics.")
    parser.add_argument("hook", choices=("pre-push",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.hook == "pre-push":
        return run_pre_push(sys.stdin)
    raise ValueError(f"Unsupported hook: {args.hook}")


if __name__ == "__main__":
    raise SystemExit(main())
