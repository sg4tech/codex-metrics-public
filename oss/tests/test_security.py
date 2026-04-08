from __future__ import annotations

import sys
from pathlib import Path

import pytest

from codex_metrics import cli
from codex_metrics.security import (
    SecurityFinding,
    SecurityReport,
    collect_staged_paths,
    load_security_rules,
    render_security_report,
    scan_security_paths,
    verify_security,
)


def _write_rules(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
forbidden_paths = []
forbidden_globs = ["logs/**"]
forbidden_extensions = [".log", ".trace", ".stderr", ".stdout"]
forbidden_literal_markers = ["-----BEGIN PRIVATE KEY-----"]
forbidden_regex_markers = ['(?i)Authorization:\\s*Bearer\\s+[A-Za-z0-9._-]{10,}', 'https?://[^\\s/:]+:[^\\s/@]+@[^\\s/]+']
ignored_paths = [".git/**", "build/**"]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_scan_security_paths_passes_clean_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "README.md").write_text("public docs\n", encoding="utf-8")
    (repo_root / "src.py").write_text("print('ok')\n", encoding="utf-8")
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["README.md", "src.py"],
    )

    assert report.findings == ()
    assert report.files_scanned == 2
    assert "passed" in render_security_report(report)


def test_scan_security_paths_detects_private_key_marker(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "secrets.md").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["secrets.md"],
    )

    assert any(finding.kind == "forbidden_marker" for finding in report.findings)
    assert any(finding.matched_rule == "-----BEGIN PRIVATE KEY-----" for finding in report.findings)


def test_scan_security_paths_detects_log_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "logs").mkdir()
    (repo_root / "logs" / "build.log").write_text("not safe\n", encoding="utf-8")
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["logs/build.log"],
    )

    assert any(finding.kind == "forbidden_path" for finding in report.findings)
    assert any(finding.matched_rule == "logs/**" for finding in report.findings)


def test_scan_security_paths_detects_shell_execution_in_python(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "script.py").write_text(
        "import subprocess\nsubprocess.run('echo hi', shell=True)\n",
        encoding="utf-8",
    )
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["script.py"],
    )

    assert any(finding.kind == "dangerous_code" for finding in report.findings)
    assert any(finding.matched_rule == "subprocess.run" for finding in report.findings)


def test_scan_security_paths_detects_shell_execution_via_import_alias(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "script.py").write_text(
        "import subprocess as sp\nsp.run('echo hi', shell=True)\n",
        encoding="utf-8",
    )
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["script.py"],
    )

    assert any(finding.kind == "dangerous_code" for finding in report.findings)
    assert any(finding.matched_rule == "subprocess.run" for finding in report.findings)


def test_scan_security_paths_detects_shell_execution_via_import_from(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "script.py").write_text(
        "from subprocess import run\nrun('echo hi', shell=True)\n",
        encoding="utf-8",
    )
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["script.py"],
    )

    assert any(finding.kind == "dangerous_code" for finding in report.findings)
    assert any(finding.matched_rule == "subprocess.run" for finding in report.findings)


def test_scan_security_paths_detects_eval_in_python(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "script.py").write_text("value = eval('1 + 1')\n", encoding="utf-8")
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["script.py"],
    )

    assert any(finding.kind == "dangerous_code" for finding in report.findings)
    assert any(finding.matched_rule == "eval" for finding in report.findings)


def test_scan_security_paths_detects_credentials_in_url(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "settings.toml").write_text(
        'endpoint = "https://alice:supersecret@example.com/api"\n',
        encoding="utf-8",
    )
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["settings.toml"],
    )

    assert any(finding.kind == "forbidden_marker" for finding in report.findings)
    assert any("https?://" in finding.matched_rule for finding in report.findings)


def test_scan_security_paths_detects_secret_assignment_in_config(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / "settings.toml").write_text('password = "swordfish"\n', encoding="utf-8")
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["settings.toml"],
    )

    assert any(finding.kind == "config_hygiene" for finding in report.findings)
    assert any(finding.matched_rule == "password" for finding in report.findings)


def test_scan_security_paths_skips_placeholder_secret_assignment_in_env_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    (repo_root / ".env").write_text("API_KEY=changeme\n", encoding="utf-8")
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=[".env"],
    )

    assert report.findings == ()


def test_scan_security_paths_skips_rules_file_itself(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    rules_path = repo_root / "config" / "security-rules.toml"
    _write_rules(rules_path)
    rules = load_security_rules(rules_path)

    report = scan_security_paths(
        repo_root=repo_root,
        rules_path=rules_path,
        rules=rules,
        candidate_paths=["config/security-rules.toml"],
    )

    assert report.findings == ()


def test_collect_staged_paths_parses_nul_separated_output(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        return type("Result", (), {"stdout": b"README.md\x00src/main.py\x00"})()

    monkeypatch.setattr("codex_metrics.security.subprocess.run", fake_run)

    paths = collect_staged_paths(tmp_path)

    assert paths == ["README.md", "src/main.py"]


def test_collect_staged_paths_decodes_non_utf8_filenames(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        return type("Result", (), {"stdout": b"bad-\xff-name.py\x00"})()

    monkeypatch.setattr("codex_metrics.security.subprocess.run", fake_run)

    paths = collect_staged_paths(tmp_path)

    assert len(paths) == 1
    assert paths[0].endswith("name.py")


def test_verify_security_requires_readable_git_index(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr("codex_metrics.security.subprocess.run", fake_run)
    rules_path = tmp_path / "config" / "security-rules.toml"
    _write_rules(rules_path)

    with pytest.raises(ValueError, match="security scan requires a readable git index"):
        verify_security(repo_root=tmp_path, rules_path=rules_path)


def test_cli_security_dispatches_and_returns_failure_exit_code(monkeypatch, capsys, tmp_path: Path) -> None:
    report = SecurityReport(
        repo_root=tmp_path,
        rules_path=tmp_path / "config" / "security-rules.toml",
        files_scanned=1,
        findings=(
            SecurityFinding(
                kind="forbidden_marker",
                path="secrets.md",
                message="file contains a forbidden literal security marker",
                matched_rule="-----BEGIN PRIVATE KEY-----",
                line=1,
            ),
        ),
    )

    monkeypatch.setattr(cli, "security", lambda *, repo_root, rules_path: report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex-metrics",
            "security",
            "--repo-root",
            str(tmp_path),
            "--rules-path",
            str(tmp_path / "config" / "security-rules.toml"),
        ],
    )

    exit_code = cli.main()

    assert exit_code == 1
    assert "Security scan failed" in capsys.readouterr().out
