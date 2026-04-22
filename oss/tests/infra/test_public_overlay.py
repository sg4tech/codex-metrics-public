from __future__ import annotations

import subprocess
from pathlib import Path

import scripts.public_overlay as public_overlay
from scripts.public_overlay import (
    build_bootstrap_commands,
    build_pull_command,
    build_push_command,
    build_status_lines,
    main,
)


def test_public_overlay_status_describes_layout(tmp_path: Path) -> None:
    private_repo_root = tmp_path / "private"
    private_repo_root.mkdir()
    (private_repo_root / "oss").mkdir()
    (private_repo_root / "oss" / "README.md").write_text("overlay\n", encoding="utf-8")

    lines = build_status_lines(
        private_repo_root=private_repo_root,
        prefix="oss",
        remote_name="public",
        branch="main",
        pr_branch="sync",
    )

    assert "overlay directory exists: yes" in lines
    assert "overlay marker exists: yes" in lines
    joined = "\n".join(lines)
    assert "git subtree push --prefix=oss public sync" in joined
    assert "sync → main" in joined
    assert "git subtree pull --prefix=oss public main --squash" in joined


def test_public_overlay_command_builders_quote_and_target_correctly(tmp_path: Path) -> None:
    public_repo = tmp_path / "codex metrics public"
    public_repo.mkdir()

    bootstrap = build_bootstrap_commands(
        public_repo=public_repo,
        remote_name="public",
        prefix="oss",
        branch="main",
    )

    assert bootstrap[0].startswith("git remote add public ")
    assert "codex metrics public'" in bootstrap[0]
    assert bootstrap[1] == "git subtree add --prefix=oss public main --squash"
    assert build_push_command(remote_name="public", prefix="oss", pr_branch="sync") == (
        "git subtree push --prefix=oss public sync"
    )
    assert build_pull_command(remote_name="public", prefix="oss", branch="main") == (
        "git subtree pull --prefix=oss public main --squash"
    )


def test_public_overlay_push_execute_runs_verify_then_push(tmp_path: Path, monkeypatch) -> None:
    private_repo_root = tmp_path / "private"
    private_repo_root.mkdir()
    (private_repo_root / "oss" / "config").mkdir(parents=True)
    (private_repo_root / "oss" / "config" / "public-boundary-rules.toml").write_text(
        'allowed_roots = ["README.md"]\n',
        encoding="utf-8",
    )
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd, check):  # noqa: ARG001
        calls.append((list(command), cwd))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(public_overlay.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--private-repo-root",
                str(private_repo_root),
                "push",
                "--execute",
            ]
        )
        == 0
    )

    assert calls[0][0][0].endswith("/.venv/bin/python")
    assert calls[0][0][-2:] == ["--rules-path", str(private_repo_root / "oss" / "config" / "public-boundary-rules.toml")]
    assert calls[1][0] == ["git", "subtree", "pull", "--prefix=oss", "public", "main", "--squash"]
    assert calls[2][0] == ["git", "subtree", "push", "--prefix=oss", "public", "sync"]
    assert calls[0][1] == private_repo_root
    assert calls[1][1] == private_repo_root
    assert calls[2][1] == private_repo_root


def test_public_overlay_mirror_includes_security_verify_and_rules() -> None:
    makefile_text = (Path(__file__).resolve().parents[2] / "Makefile").read_text(
        encoding="utf-8"
    )
    rules_text = (Path(__file__).resolve().parents[2] / "config" / "security-rules.toml").read_text(
        encoding="utf-8"
    )

    assert "security:" in makefile_text
    assert "verify:" in makefile_text
    assert "lint" in makefile_text
    assert "security" in makefile_text
    assert "typecheck" in makefile_text
    assert "verify-public-boundary" in makefile_text
    assert "forbidden_literal_markers" in rules_text
