"""CLAUDE.md must be a symlink pointing to AGENTS.md — never a standalone file."""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def test_claude_md_exists():
    assert CLAUDE_MD.exists(), "CLAUDE.md must exist"


def test_claude_md_is_symlink_to_agents():
    assert CLAUDE_MD.is_symlink(), (
        "CLAUDE.md must be a symlink to AGENTS.md, not a standalone file. "
        "To update project rules, edit AGENTS.md only."
    )
    assert CLAUDE_MD.resolve() == (REPO_ROOT / "AGENTS.md").resolve(), (
        f"CLAUDE.md symlink must point to AGENTS.md, got: {CLAUDE_MD.readlink()}"
    )
