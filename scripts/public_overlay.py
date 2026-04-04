#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

DEFAULT_PRIVATE_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC_REPO = Path("../codex-metrics-public")
DEFAULT_REMOTE_NAME = "public"
DEFAULT_BRANCH = "main"
DEFAULT_PREFIX = "oss"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan private/public subtree sync commands.")
    parser.add_argument(
        "--private-repo-root",
        default=str(DEFAULT_PRIVATE_REPO_ROOT),
        help="Path to the private repository root.",
    )
    parser.add_argument(
        "--public-repo",
        default=str(DEFAULT_PUBLIC_REPO),
        help="Path to the sibling public repository.",
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
    subparsers.add_parser("bootstrap", help="Print the initial subtree import commands.")
    subparsers.add_parser("push", help="Print the command used to publish private subtree changes.")
    subparsers.add_parser("pull", help="Print the command used to pull public changes into private.")
    return parser


def format_private_repo_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def quote_path(path: Path) -> str:
    return shlex.quote(str(path))


def build_status_lines(*, private_repo_root: Path, public_repo: Path, prefix: str, remote_name: str, branch: str) -> list[str]:
    overlay_root = private_repo_root / prefix
    lines = [
        f"private repo root: {private_repo_root}",
        f"public repo root: {public_repo}",
        f"overlay prefix: {prefix}/",
        f"overlay directory exists: {'yes' if overlay_root.exists() else 'no'}",
        f"overlay marker exists: {'yes' if (overlay_root / 'README.md').exists() else 'no'}",
        f"recommended remote name: {remote_name}",
        f"recommended branch: {branch}",
        "",
        "initial import:",
        f"  git remote add {remote_name} {quote_path(public_repo)}",
        f"  git subtree add --prefix={prefix} {remote_name} {branch} --squash",
        "",
        "sync from private to public:",
        f"  git subtree push --prefix={prefix} {remote_name} {branch}",
        "",
        "sync from public to private:",
        f"  git subtree pull --prefix={prefix} {remote_name} {branch} --squash",
    ]
    return lines


def build_bootstrap_commands(*, public_repo: Path, remote_name: str, prefix: str, branch: str) -> list[str]:
    return [
        f"git remote add {remote_name} {quote_path(public_repo)}",
        f"git subtree add --prefix={prefix} {remote_name} {branch} --squash",
    ]


def build_push_command(*, remote_name: str, prefix: str, branch: str) -> str:
    return f"git subtree push --prefix={prefix} {remote_name} {branch}"


def build_pull_command(*, remote_name: str, prefix: str, branch: str) -> str:
    return f"git subtree pull --prefix={prefix} {remote_name} {branch} --squash"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    private_repo_root = format_private_repo_root(args.private_repo_root)
    public_repo = Path(args.public_repo).expanduser().resolve()

    if args.command == "status":
        for line in build_status_lines(
            private_repo_root=private_repo_root,
            public_repo=public_repo,
            prefix=args.prefix,
            remote_name=args.remote_name,
            branch=args.branch,
        ):
            print(line)
        return 0

    if args.command == "bootstrap":
        for line in build_bootstrap_commands(
            public_repo=public_repo,
            remote_name=args.remote_name,
            prefix=args.prefix,
            branch=args.branch,
        ):
            print(line)
        return 0

    if args.command == "push":
        print(build_push_command(remote_name=args.remote_name, prefix=args.prefix, branch=args.branch))
        return 0

    if args.command == "pull":
        print(build_pull_command(remote_name=args.remote_name, prefix=args.prefix, branch=args.branch))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
