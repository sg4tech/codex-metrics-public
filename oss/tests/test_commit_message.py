from __future__ import annotations

from pathlib import Path

from codex_metrics.commit_message import (
    validate_commit_message_file,
    validate_commit_message_text,
    validate_commit_subject,
)


def test_validate_commit_subject_accepts_linear_linked_subject() -> None:
    result = validate_commit_subject("CODEX-123: update commit hook validation")
    assert result.allowed is True
    assert result.reason is None


def test_validate_commit_subject_accepts_explicit_no_task_subject() -> None:
    result = validate_commit_subject("NO-TASK: docs-only policy wording")
    assert result.allowed is True
    assert result.reason is None


def test_validate_commit_subject_rejects_linear_subject_for_retro_only_commit() -> None:
    result = validate_commit_subject(
        "CODEX-123: retro cleanup",
        staged_paths=["docs/retros/2026-04-03-example.md"],
    )
    assert result.allowed is False
    assert "Retrospective-only commits must use NO-TASK: summary." in result.reason


def test_validate_commit_subject_accepts_no_task_subject_for_retro_only_commit() -> None:
    result = validate_commit_subject(
        "NO-TASK: add retrospective",
        staged_paths=["docs/retros/2026-04-03-example.md"],
    )
    assert result.allowed is True
    assert result.reason is None


def test_validate_commit_subject_allows_linear_subject_when_retro_is_mixed_with_other_work() -> None:
    result = validate_commit_subject(
        "CODEX-123: ship fix with retro",
        staged_paths=["docs/retros/2026-04-03-example.md", "src/codex_metrics/commit_message.py"],
    )
    assert result.allowed is True
    assert result.reason is None


def test_validate_commit_subject_rejects_unmarked_subject() -> None:
    result = validate_commit_subject("update commit hook validation")
    assert result.allowed is False
    assert "CODEX-123: summary" in result.reason
    assert "NO-TASK: summary" in result.reason


def test_validate_commit_subject_accepts_merge_commits() -> None:
    result = validate_commit_subject('Merge branch "feature/commit-hooks"')
    assert result.allowed is True


def test_validate_commit_message_text_uses_first_non_comment_line() -> None:
    result = validate_commit_message_text(
        "\n# Please enter the commit message for your changes. Lines starting\nCODEX-42: add hook validation\n"
    )
    assert result.allowed is True


def test_validate_commit_message_file_rejects_empty_message(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("\n# comment only\n", encoding="utf-8")

    result = validate_commit_message_file(message_file)
    assert result.allowed is False
    assert "Commit subject is empty" in result.reason
