#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

DEFAULT_PRIVATE_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_NAME = "public"
DEFAULT_BRANCH = "main"
DEFAULT_PULL_BRANCHES = ["main", "sync"]
DEFAULT_PR_BRANCH = "sync"
DEFAULT_PREFIX = "oss"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan private/public subtree sync commands.")
    parser.add_argument(
        "--private-repo-root",
        default=str(DEFAULT_PRIVATE_REPO_ROOT),
        help="Path to the private repository root.",
    )
    parser.add_argument(
        "--remote-name",
        default=DEFAULT_REMOTE_NAME,
        help="Git remote name to use for the public repository.",
    )
    parser.add_argument(
        "--branch",
        default=DEFAULT_BRANCH,
        help="Public repository branch to sync against.",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help="Private repository directory that will hold the subtree mirror.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Summarize the intended overlay layout.")
    bootstrap_parser = subparsers.add_parser("bootstrap", help="Print the initial subtree import commands.")
    bootstrap_parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the bootstrap commands instead of only printing them.",
    )
    bootstrap_parser.add_argument(
        "--public-repo",
        required=True,
        help="URL or path of the public repository (used for git remote add).",
    )
    push_parser = subparsers.add_parser("push", help="Print the command used to publish private subtree changes.")
    push_parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the subtree push instead of only printing the planned shell command.",
    )
    push_parser.add_argument(
        "--pr-branch",
        default=DEFAULT_PR_BRANCH,
        help=f"Branch to push to on the public remote (default: {DEFAULT_PR_BRANCH}). Open a PR from this branch into main.",
    )
    pull_parser = subparsers.add_parser("pull", help="Print the command used to pull public changes into private.")
    pull_parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the subtree pull instead of only printing the planned shell command.",
    )
    pull_parser.add_argument(
        "--branches",
        nargs="+",
        default=DEFAULT_PULL_BRANCHES,
        metavar="BRANCH",
        help=f"Branches to pull from the public remote (default: {' '.join(DEFAULT_PULL_BRANCHES)}). "
             "Branches other than the first are skipped if not found on the remote.",
    )
    return parser


def format_private_repo_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def quote_path(path: Path) -> str:
    return shlex.quote(str(path))


def build_status_lines(*, private_repo_root: Path, prefix: str, remote_name: str, branch: str, pr_branch: str) -> list[str]:
    overlay_root = private_repo_root / prefix
    lines = [
        f"private repo root: {private_repo_root}",
        f"overlay prefix: {prefix}/",
        f"overlay directory exists: {'yes' if overlay_root.exists() else 'no'}",
        f"overlay marker exists: {'yes' if (overlay_root / 'README.md').exists() else 'no'}",
        f"recommended remote name: {remote_name}",
        f"public base branch: {branch}",
        f"push PR branch: {pr_branch}",
        "",
        "sync from private to public (creates/updates PR branch):",
        f"  git subtree push --prefix={prefix} {remote_name} {pr_branch}",
        f"  then open a PR: {pr_branch} → {branch}",
        "",
        "sync from public to private (after PR is merged):",
        f"  git subtree pull --prefix={prefix} {remote_name} {branch} --squash",
    ]
    return lines


def build_bootstrap_commands(*, public_repo: Path, remote_name: str, prefix: str, branch: str) -> list[str]:
    return [
        f"git remote add {remote_name} {quote_path(public_repo)}",
        f"git subtree add --prefix={prefix} {remote_name} {branch} --squash",
    ]


def build_push_command(*, remote_name: str, prefix: str, pr_branch: str) -> str:
    return f"git subtree push --prefix={prefix} {remote_name} {pr_branch}"


def build_pull_command(*, remote_name: str, prefix: str, branch: str) -> str:
    return f"git subtree pull --prefix={prefix} {remote_name} {branch} --squash"


def _remote_branch_exists(*, remote_name: str, branch: str, cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", remote_name, branch],
        cwd=cwd,
        capture_output=True,
    )
    return result.returncode == 0


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _verify_public_boundary(*, private_repo_root: Path, prefix: str) -> None:
    rules_path = private_repo_root / prefix / "config" / "public-boundary-rules.toml"
    _run(
        [
            str(private_repo_root / ".venv" / "bin" / "python"),
            "-m",
            "ai_agents_metrics",
            "verify-public-boundary",
            "--repo-root",
            str(private_repo_root / prefix),
            "--rules-path",
            str(rules_path),
        ],
        cwd=private_repo_root,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    private_repo_root = format_private_repo_root(args.private_repo_root)

    if args.command == "status":
        pr_branch = getattr(args, "pr_branch", DEFAULT_PR_BRANCH)
        for line in build_status_lines(
            private_repo_root=private_repo_root,
            prefix=args.prefix,
            remote_name=args.remote_name,
            branch=args.branch,
            pr_branch=pr_branch,
        ):
            print(line)
        return 0

    if args.command == "bootstrap":
        public_repo = Path(args.public_repo).expanduser().resolve()
        commands = build_bootstrap_commands(
            public_repo=public_repo,
            remote_name=args.remote_name,
            prefix=args.prefix,
            branch=args.branch,
        )
        if args.execute:
            _run(shlex.split(commands[0]), cwd=private_repo_root)
            _run(shlex.split(commands[1]), cwd=private_repo_root)
        else:
            for line in commands:
                print(line)
        return 0

    if args.command == "push":
        command = build_push_command(remote_name=args.remote_name, prefix=args.prefix, pr_branch=args.pr_branch)
        if args.execute:
            _verify_public_boundary(private_repo_root=private_repo_root, prefix=args.prefix)
            _run(shlex.split(command), cwd=private_repo_root)
        else:
            print(command)
        return 0

    if args.command == "pull":
        branches: list[str] = args.branches
        if args.execute:
            for i, branch in enumerate(branches):
                required = i == 0
                if not required and not _remote_branch_exists(
                    remote_name=args.remote_name, branch=branch, cwd=private_repo_root
                ):
                    print(f"public-overlay-pull: branch '{branch}' not found on remote '{args.remote_name}', skipping")
                    continue
                _run(shlex.split(build_pull_command(remote_name=args.remote_name, prefix=args.prefix, branch=branch)), cwd=private_repo_root)
            _verify_public_boundary(private_repo_root=private_repo_root, prefix=args.prefix)
        else:
            for branch in branches:
                print(build_pull_command(remote_name=args.remote_name, prefix=args.prefix, branch=branch))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
