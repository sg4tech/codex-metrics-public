"""Installers and checkers for the project-managed git hooks under .githooks/."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

ZERO_OID = "0" * 40

_RULES_PATH = Path("config") / "public-boundary-rules.toml"


def normalize_repo_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


class GitHookRunner:
    def git_lines(self, args: Sequence[str]) -> list[str]:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def repo_root(self) -> Path:
        lines = self.git_lines(["rev-parse", "--show-toplevel"])
        return Path(lines[0])

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

    def run_security_scan(self, changed_paths: list[str]) -> int:
        root = self.repo_root()
        rules_path = root / _RULES_PATH
        if not rules_path.exists():
            print("pre-push: no public boundary rules found; skipping security scan")
            return 0

        raw_rules = tomllib.loads(rules_path.read_text(encoding="utf-8"))
        literal_markers: list[str] = raw_rules.get("forbidden_literal_markers", [])
        regex_patterns = [re.compile(p) for p in raw_rules.get("forbidden_regex_markers", [])]
        marker_ignored: set[str] = set(raw_rules.get("marker_ignored_paths", []))
        marker_ignored.add(_RULES_PATH.as_posix())

        violations: list[str] = []
        scanned = 0

        for rel_path in changed_paths:
            if rel_path in marker_ignored:
                continue
            abs_path = root / rel_path
            if not abs_path.is_file():
                continue
            try:
                raw = abs_path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            scanned += 1

            for marker in literal_markers:
                idx = text.find(marker)
                if idx != -1:
                    line_no = text.count("\n", 0, idx) + 1
                    violations.append(f"  {rel_path}:{line_no}: forbidden marker {marker!r}")

            for pattern in regex_patterns:
                match = pattern.search(text)
                if match:
                    line_no = text.count("\n", 0, match.start()) + 1
                    violations.append(f"  {rel_path}:{line_no}: matches forbidden pattern {pattern.pattern!r}")

        if violations:
            print(f"pre-push: security scan FAILED — {len(violations)} violation(s):")
            for v in violations:
                print(v)
            return 1

        print(f"pre-push: security scan passed ({scanned} file(s) scanned)")
        return 0


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

    return hook_runner.run_security_scan(changed_paths)


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
