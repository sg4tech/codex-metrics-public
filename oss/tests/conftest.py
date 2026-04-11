from __future__ import annotations

import sys
from pathlib import Path

# Ensure oss/tests/ is importable by its real path so that cross-test imports
# like `from test_history_ingest import ...` work regardless of whether tests
# run from oss/ directly or from the root repo via the tests/public/ symlink.
_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
