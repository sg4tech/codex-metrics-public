.PHONY: lint typecheck test verify coverage package

lint:
	./.venv/bin/ruff check .

typecheck:
	./.venv/bin/mypy src scripts

test:
	./.venv/bin/python -m pytest tests/test_update_codex_metrics.py tests/test_update_codex_metrics_domain.py

verify: lint typecheck test

coverage:
	./.venv/bin/coverage erase
	CODEX_SUBPROCESS_COVERAGE=1 ./.venv/bin/coverage run -m pytest tests/test_update_codex_metrics.py tests/test_update_codex_metrics_domain.py
	./.venv/bin/coverage combine
	./.venv/bin/coverage report -m src/codex_metrics/cli.py scripts/update_codex_metrics.py

package:
	rm -rf build dist src/codex_metrics.egg-info
	./.venv/bin/python -m build --no-isolation
