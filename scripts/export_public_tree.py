#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_EXCLUDED_TOP_LEVEL = {
    ".github",
    ".githooks",
    "AGENTS.md",
    "docs",
    "metrics",
    "scripts",
    "tools",
}

DEFAULT_INCLUDED_PATHS = {
    ".gitignore",
    "LICENSE",
    "Makefile",
    "README.md",
    "config/public-boundary-rules.toml",
    "config/security-rules.toml",
    "pricing",
    "pyproject.toml",
    "src",
    "tests/test_public_boundary.py",
}

LICENSE_TEXT = """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions.

"License" shall mean the terms and conditions for use, reproduction, and distribution as defined by Sections 1 through 9 of this document.

"Licensor" shall mean the copyright owner or entity authorized by the copyright owner that is granting the License.

"Legal Entity" shall mean the union of the acting entity and all other entities that control, are controlled by, or are under common control with that entity.

"You" (or "Your") shall mean an individual or Legal Entity exercising permissions granted by this License.

"Source" form shall mean the preferred form for making modifications, including but not limited to software source code, documentation source, and configuration files.

"Object" form shall mean any form resulting from mechanical transformation or translation of a Source form, including but not limited to compiled object code, generated documentation, and conversions to other media types.

"Work" shall mean the work of authorship, whether in Source or Object form, made available under the License, as indicated by a copyright notice that is included in or attached to the work.

"Derivative Works" shall mean any work, whether in Source or Object form, that is based on the Work and for which the editorial revisions, annotations, elaborations, or other modifications represent, as a whole, an original work of authorship.

"Contribution" shall mean any work of authorship, including the original version of the Work and any modifications or additions to that Work or Derivative Works thereof, that is intentionally submitted to Licensor for inclusion in the Work by the copyright owner or by an individual or Legal Entity authorized to submit on behalf of the copyright owner.

"Contributor" shall mean Licensor and any individual or Legal Entity on behalf of whom a Contribution has been received by Licensor and subsequently incorporated within the Work.

2. Grant of Copyright License.
Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work and such Derivative Works in Source or Object form.

3. Grant of Patent License.
Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except as stated in this section) patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work.

4. Redistribution.
You may reproduce and distribute copies of the Work or Derivative Works thereof in any medium, with or without modifications, and in Source or Object form, provided that You meet the following conditions:

   a. You must give any other recipients of the Work or Derivative Works a copy of this License; and

   b. You must cause any modified files to carry prominent notices stating that You changed the files; and

   c. You must retain, in the Source form of any Derivative Works that You distribute, all copyright, patent, trademark, and attribution notices from the Source form of the Work, excluding those notices that do not pertain to any part of the Derivative Works; and

   d. If the Work includes a "NOTICE" text file as part of its distribution, then any Derivative Works that You distribute must include a readable copy of the attribution notices contained within such NOTICE file.

5. Submission of Contributions.
Unless You explicitly state otherwise, any Contribution intentionally submitted for inclusion in the Work by You to the Licensor shall be under the terms and conditions of this License, without any additional terms or conditions.

6. Trademarks.
This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor, except as required for reasonable and customary use in describing the origin of the Work and reproducing the content of the NOTICE file.

7. Disclaimer of Warranty.
Unless required by applicable law or agreed to in writing, Licensor provides the Work on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

8. Limitation of Liability.
In no event and under no legal theory, whether in tort (including negligence), contract, or otherwise, unless required by applicable law or agreed to in writing, shall any Contributor be liable for damages arising from the License or the use of the Work.

9. Accepting Warranty or Additional Liability.
While redistributing the Work or Derivative Works thereof, You may choose to offer, and charge a fee for, acceptance of support, warranty, indemnity, or other liability obligations and/or rights consistent with this License.

END OF TERMS AND CONDITIONS
"""

WORKFLOW_TEXT = """name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - name: Install
        run: python -m pip install -e . ruff mypy pytest
      - name: Verify
        run: make verify
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a minimal public tree from the repository.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", default="build/public-tree")
    parser.add_argument("--include-docs", action="store_true", help="Include docs/ in the exported tree.")
    return parser


def export_public_tree(*, repo_root: Path, output_dir: Path, include_docs: bool) -> list[str]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    included_paths = set(DEFAULT_INCLUDED_PATHS)
    if include_docs:
        included_paths.add("docs")

    copied: list[str] = []
    for relative_path in sorted(included_paths):
        source = repo_root / relative_path
        destination = output_dir / relative_path
        if relative_path == "README.md":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                "# codex-metrics\n\n"
                "Open-source core for tracking AI-agent-assisted engineering work.\n",
                encoding="utf-8",
            )
            copied.append(relative_path)
            continue
        if relative_path == "LICENSE":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(LICENSE_TEXT, encoding="utf-8")
            copied.append(relative_path)
            continue
        if relative_path == "Makefile":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                ".PHONY: lint security typecheck test verify verify-public-boundary\n\n"
                "lint:\n"
                "\tpython -m ruff check .\n\n"
                "security:\n"
                "\tpython -m codex_metrics security --repo-root . --rules-path config/security-rules.toml\n\n"
                "typecheck:\n"
                "\tpython -m mypy src\n\n"
                "test:\n"
                "\tpython -m pytest tests/test_public_boundary.py\n\n"
                "verify-public-boundary:\n"
                "\tpython -m codex_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml\n\n"
                "verify: lint security typecheck test verify-public-boundary\n",
                encoding="utf-8",
            )
            copied.append(relative_path)
            continue
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    "*.egg-info",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                ),
            )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        copied.append(relative_path)

    workflow_path = output_dir / ".github" / "workflows" / "ci.yml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(WORKFLOW_TEXT, encoding="utf-8")
    copied.append(".github/workflows/ci.yml")
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    copied = export_public_tree(repo_root=repo_root, output_dir=output_dir, include_docs=args.include_docs)
    print(f"Exported minimal public tree to {output_dir}")
    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
