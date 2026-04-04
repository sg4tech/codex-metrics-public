from __future__ import annotations

from pathlib import Path

from codex_metrics.git_hooks import (
    GitHookRunner,
    run_pre_push,
)


class FakeGitHookRunner(GitHookRunner):
    def __init__(
        self,
        paths_by_ref: dict[tuple[str, str], list[str]],
        scan_returncode: int = 0,
    ) -> None:
        self.paths_by_ref = paths_by_ref
        self.scan_returncode = scan_returncode
        self.scan_calls: list[list[str]] = []

    def changed_paths_for_ref_update(self, local_sha: str, remote_sha: str) -> list[str]:
        return self.paths_by_ref[(local_sha, remote_sha)]

    def run_security_scan(self, changed_paths: list[str]) -> int:
        self.scan_calls.append(list(changed_paths))
        return self.scan_returncode


def test_run_pre_push_calls_security_scan_for_code_changes() -> None:
    runner = FakeGitHookRunner(
        {
            ("abc123", "def456"): [
                "src/codex_metrics/git_hooks.py",
                "README.md",
            ]
        }
    )

    exit_code = run_pre_push(["refs/heads/main abc123 refs/remotes/origin/main def456\n"], runner=runner)

    assert exit_code == 0
    assert runner.scan_calls == [["src/codex_metrics/git_hooks.py", "README.md"]]


def test_run_pre_push_calls_security_scan_for_docs_only_changes() -> None:
    runner = FakeGitHookRunner(
        {
            ("abc123", "def456"): [
                "README.md",
                "docs/retros/2026-04-03-example.md",
            ]
        }
    )

    exit_code = run_pre_push(["refs/heads/main abc123 refs/remotes/origin/main def456\n"], runner=runner)

    assert exit_code == 0
    assert runner.scan_calls == [["README.md", "docs/retros/2026-04-03-example.md"]]


def test_run_pre_push_deduplicates_paths_across_ref_updates() -> None:
    runner = FakeGitHookRunner(
        {
            ("abc123", "def456"): ["src/codex_metrics/git_hooks.py"],
            ("abc124", "def457"): ["src/codex_metrics/git_hooks.py", "tests/test_git_hooks.py"],
        }
    )

    run_pre_push(
        [
            "refs/heads/main abc123 refs/remotes/origin/main def456\n",
            "refs/heads/feature abc124 refs/remotes/origin/feature def457\n",
        ],
        runner=runner,
    )

    assert runner.scan_calls == [["src/codex_metrics/git_hooks.py", "tests/test_git_hooks.py"]]


def test_run_pre_push_propagates_scan_failure() -> None:
    runner = FakeGitHookRunner(
        {("abc123", "def456"): ["src/codex_metrics/git_hooks.py"]},
        scan_returncode=1,
    )

    exit_code = run_pre_push(["refs/heads/main abc123 refs/remotes/origin/main def456\n"], runner=runner)

    assert exit_code == 1


# --- run_security_scan tests ---

MINIMAL_RULES_TOML = """\
forbidden_literal_markers = ["Internal only", "Do not publish"]
forbidden_regex_markers = ["/Users/[^/]+/PycharmProjects/"]
marker_ignored_paths = ["tests/test_public_boundary.py"]
"""


def _make_runner_with_root(monkeypatch, tmp_path: Path) -> GitHookRunner:
    runner = GitHookRunner()
    monkeypatch.setattr(runner, "repo_root", lambda: tmp_path)
    return runner


def test_run_security_scan_passes_clean_file(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)
    (tmp_path / "src.py").write_text("def hello(): pass\n")

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["src.py"])

    assert result == 0
    assert "passed" in capsys.readouterr().out


def test_run_security_scan_detects_literal_marker(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)
    (tmp_path / "notes.md").write_text("Internal only: pricing model\n")

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["notes.md"])

    assert result == 1
    assert "Internal only" in capsys.readouterr().out


def test_run_security_scan_detects_regex_marker(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)
    (tmp_path / "debug.py").write_text('PATH = "/Users/viktor/PycharmProjects/codex-metrics"\n')

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["debug.py"])

    assert result == 1
    assert "PycharmProjects" in capsys.readouterr().out


def test_run_security_scan_skips_deleted_files(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["deleted.py"])

    assert result == 0


def test_run_security_scan_skips_binary_files(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)
    (tmp_path / "data.bin").write_bytes(b"Internal only\x00binary content")

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["data.bin"])

    assert result == 0


def test_run_security_scan_skips_rules_file_itself(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["config/public-boundary-rules.toml"])

    assert result == 0


def test_run_security_scan_skips_marker_ignored_paths(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "public-boundary-rules.toml").write_text(MINIMAL_RULES_TOML)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_public_boundary.py").write_text('marker = "Internal only"\n')

    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["tests/test_public_boundary.py"])

    assert result == 0


def test_run_security_scan_no_rules_file_skips_gracefully(monkeypatch, tmp_path: Path, capsys) -> None:
    runner = _make_runner_with_root(monkeypatch, tmp_path)
    result = runner.run_security_scan(["src.py"])

    assert result == 0
    assert "skipping" in capsys.readouterr().out
