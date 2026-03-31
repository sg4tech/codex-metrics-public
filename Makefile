.PHONY: lint typecheck test verify coverage package package-standalone package-refresh-local package-refresh-global live-usage-smoke

lint:
	./.venv/bin/ruff check .

typecheck:
	./.venv/bin/mypy src scripts

test:
	./.venv/bin/python -m pytest tests/test_update_codex_metrics.py tests/test_update_codex_metrics_domain.py tests/test_history_audit.py

verify: lint typecheck test

coverage:
	./.venv/bin/coverage erase
	CODEX_SUBPROCESS_COVERAGE=1 ./.venv/bin/coverage run -m pytest tests/test_update_codex_metrics.py tests/test_update_codex_metrics_domain.py tests/test_history_audit.py
	./.venv/bin/coverage combine
	./.venv/bin/coverage report -m

package:
	rm -rf build dist src/codex_metrics.egg-info
	./.venv/bin/python -m build --no-isolation

package-standalone:
	rm -rf build/standalone dist/standalone
	./.venv/bin/python scripts/build_standalone.py

package-refresh-local: package
	./.venv/bin/python -m pip install --no-deps --force-reinstall dist/*.whl

package-refresh-global: package-refresh-local package-standalone
	./dist/standalone/codex-metrics install-self $(INSTALL_SELF_ARGS)

live-usage-smoke:
	./.venv/bin/python scripts/check_live_usage_recovery.py
