from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from codex_metrics import storage


def test_metrics_file_immutability_guard_unlocks_and_relocks_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_immutability_command() -> tuple[list[str], list[str]]:
        return (["fake-unlock"], ["fake-lock"])

    def fake_run(args: list[str], *, check: bool, capture_output: bool, text: bool) -> None:
        calls.append(args)
        assert check is True
        assert capture_output is True
        assert text is True

    monkeypatch.setattr(storage, "_immutability_command", fake_immutability_command)
    monkeypatch.setattr(storage.subprocess, "run", fake_run)

    with storage.metrics_file_immutability_guard(metrics_path):
        calls.append(["body"])

    assert calls == [
        ["fake-unlock", str(metrics_path)],
        ["body"],
        ["fake-lock", str(metrics_path)],
    ]


def test_metrics_file_immutability_guard_relocks_after_body_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_immutability_command() -> tuple[list[str], list[str]]:
        return (["fake-unlock"], ["fake-lock"])

    def fake_run(args: list[str], *, check: bool, capture_output: bool, text: bool) -> None:
        calls.append(args)
        assert check is True
        assert capture_output is True
        assert text is True

    monkeypatch.setattr(storage, "_immutability_command", fake_immutability_command)
    monkeypatch.setattr(storage.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        with storage.metrics_file_immutability_guard(metrics_path):
            raise RuntimeError("boom")

    assert calls == [
        ["fake-unlock", str(metrics_path)],
        ["fake-lock", str(metrics_path)],
    ]


def test_immutability_command_returns_none_when_command_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage.os, "name", "posix", raising=False)
    monkeypatch.setattr(storage.os, "uname", lambda: type("Uname", (), {"sysname": "Darwin"})(), raising=False)
    monkeypatch.setattr(storage.shutil, "which", lambda command: None)

    assert storage._immutability_command() is None


def test_immutability_command_selects_linux_chattr_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage.os, "name", "posix", raising=False)
    monkeypatch.setattr(storage.os, "uname", lambda: type("Uname", (), {"sysname": "Linux"})(), raising=False)
    monkeypatch.setattr(storage.shutil, "which", lambda command: f"/usr/bin/{command}")

    assert storage._immutability_command() == (["chattr", "-i"], ["chattr", "+i"])


def test_immutability_command_returns_none_on_non_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage.os, "name", "nt", raising=False)

    assert storage._immutability_command() is None


def test_metrics_mutation_lock_uses_lockfile_and_releases_after_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    lock_path = storage.metrics_lock_path(metrics_path)
    calls: list[tuple[str, str]] = []

    def fake_flock(fd: int, mode: int) -> None:
        calls.append(("flock", str(mode)))

    def fake_sleep(seconds: float) -> None:
        calls.append(("sleep", str(seconds)))

    monkeypatch.setattr(storage.fcntl, "flock", fake_flock)
    monkeypatch.setattr(storage.time, "sleep", fake_sleep)
    monkeypatch.setenv("CODEX_METRICS_DEBUG_LOCK_HOLD_SECONDS", "0.1")

    with storage.metrics_mutation_lock(metrics_path):
        calls.append(("body", str(lock_path)))

    assert lock_path.exists()
    assert calls == [
        ("flock", str(storage.fcntl.LOCK_EX)),
        ("sleep", "0.1"),
        ("body", str(lock_path)),
        ("flock", str(storage.fcntl.LOCK_UN)),
    ]


def test_save_metrics_uses_metrics_file_immutability_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    calls: list[tuple[str, Path]] = []

    @contextmanager
    def metrics_file_immutability_guard(path: Path):
        calls.append(("enter", path))
        yield
        calls.append(("exit", path))

    monkeypatch.setattr(storage, "metrics_file_immutability_guard", metrics_file_immutability_guard, raising=False)

    written: dict[str, object] = {}

    def fake_atomic_write_text(path: Path, content: str) -> None:
        written["path"] = path
        written["content"] = content

    monkeypatch.setattr(storage, "atomic_write_text", fake_atomic_write_text)

    storage.save_metrics(metrics_path, {"summary": {}, "goals": [], "entries": []})

    assert calls == [("enter", metrics_path), ("exit", metrics_path)]
    assert written["path"] == metrics_path


def test_save_metrics_relocks_after_failed_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    calls: list[tuple[str, Path]] = []

    @contextmanager
    def metrics_file_immutability_guard(path: Path):
        calls.append(("enter", path))
        try:
            yield
        finally:
            calls.append(("exit", path))

    monkeypatch.setattr(storage, "metrics_file_immutability_guard", metrics_file_immutability_guard, raising=False)

    def fake_atomic_write_text(path: Path, content: str) -> None:
        raise PermissionError(f"simulated immutable file: {path}")

    monkeypatch.setattr(storage, "atomic_write_text", fake_atomic_write_text)

    with pytest.raises(PermissionError):
        storage.save_metrics(metrics_path, {"summary": {}, "goals": [], "entries": []})

    assert calls == [("enter", metrics_path), ("exit", metrics_path)]
