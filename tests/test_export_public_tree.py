from __future__ import annotations

from pathlib import Path

from scripts.export_public_tree import export_public_tree


def test_export_public_tree_excludes_docs_by_default(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("readme\n", encoding="utf-8")
    (repo_root / "Makefile").write_text("verify:\n\t@true\n", encoding="utf-8")
    (repo_root / "src").mkdir()
    (repo_root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (repo_root / "config").mkdir()
    (repo_root / "config" / "public-boundary-rules.toml").write_text(
        "allowed_roots = [\"README.md\", \"src\"]\n",
        encoding="utf-8",
    )
    (repo_root / "tests").mkdir()
    (repo_root / "tests" / "test_public_boundary.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "retros").mkdir()
    (repo_root / "docs" / "retros" / "private.md").write_text("private\n", encoding="utf-8")

    output_dir = tmp_path / "public-tree"
    copied = export_public_tree(repo_root=repo_root, output_dir=output_dir, include_docs=False)

    assert "README.md" in copied
    assert "LICENSE" in copied
    assert "src" in copied
    assert "docs" not in copied
    assert "config/public-boundary-rules.toml" in copied
    assert "tests/test_public_boundary.py" in copied
    assert (output_dir / "README.md").exists()
    assert (output_dir / "LICENSE").exists()
    assert (output_dir / "src" / "main.py").exists()
    assert (output_dir / "config" / "public-boundary-rules.toml").exists()
    assert (output_dir / "tests" / "test_public_boundary.py").exists()
    makefile_text = (output_dir / "Makefile").read_text(encoding="utf-8")
    assert "verify-public-boundary" in makefile_text
    assert "test:" in makefile_text
    assert (output_dir / ".github" / "workflows" / "ci.yml").exists()
    assert not (output_dir / "docs").exists()


def test_export_public_tree_can_include_docs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("readme\n", encoding="utf-8")
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "guide.md").write_text("public guide\n", encoding="utf-8")

    output_dir = tmp_path / "public-tree"
    copied = export_public_tree(repo_root=repo_root, output_dir=output_dir, include_docs=True)

    assert "docs" in copied
    assert (output_dir / "docs" / "guide.md").exists()
