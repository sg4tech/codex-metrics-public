from __future__ import annotations

from pathlib import Path

from scripts.public_overlay import (
    build_bootstrap_commands,
    build_pull_command,
    build_push_command,
    build_status_lines,
)


def test_public_overlay_status_describes_layout(tmp_path: Path) -> None:
    private_repo_root = tmp_path / "private"
    private_repo_root.mkdir()
    (private_repo_root / "oss").mkdir()
    (private_repo_root / "oss" / "README.md").write_text("overlay\n", encoding="utf-8")
    public_repo = tmp_path / "public"
    public_repo.mkdir()

    lines = build_status_lines(
        private_repo_root=private_repo_root,
        public_repo=public_repo,
        prefix="oss",
        remote_name="public",
        branch="main",
    )

    assert "overlay directory exists: yes" in lines
    assert "overlay marker exists: yes" in lines
    assert f"git remote add public {public_repo}" in "\n".join(lines)
    joined = "\n".join(lines)
    assert "git subtree add --prefix=oss public main --squash" in joined
    assert "git subtree push --prefix=oss public main" in joined
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
    assert build_push_command(remote_name="public", prefix="oss", branch="main") == (
        "git subtree push --prefix=oss public main"
    )
    assert build_pull_command(remote_name="public", prefix="oss", branch="main") == (
        "git subtree pull --prefix=oss public main --squash"
    )
