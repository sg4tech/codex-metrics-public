.PHONY: lint typecheck test verify verify-public-boundary export-public-tree public-overlay-status public-overlay-bootstrap public-overlay-verify public-overlay-push public-overlay-pull coverage dev-refresh-local package package-standalone package-refresh-local package-refresh-global live-usage-smoke

lint:
	./.venv/bin/ruff check .

typecheck:
	./.venv/bin/mypy src scripts

test:
	./.venv/bin/python -m pytest tests/

verify: lint typecheck test

verify-public-boundary:
	@test -n "$(PUBLIC_BOUNDARY_ROOT)" || (echo "Set PUBLIC_BOUNDARY_ROOT to the candidate public repository root before running make verify-public-boundary." && exit 2)
	./.venv/bin/python -m codex_metrics verify-public-boundary --repo-root "$(PUBLIC_BOUNDARY_ROOT)" --rules-path config/public-boundary-rules.toml

export-public-tree:
	./.venv/bin/python scripts/export_public_tree.py --output-dir build/public-tree

public-overlay-status:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . --public-repo ../codex-metrics-public status

public-overlay-bootstrap:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . --public-repo ../codex-metrics-public bootstrap

public-overlay-verify:
	./.venv/bin/python -m codex_metrics verify-public-boundary --repo-root oss --rules-path oss/config/public-boundary-rules.toml

public-overlay-push:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . --public-repo ../codex-metrics-public push --execute

public-overlay-pull:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . --public-repo ../codex-metrics-public pull --execute

coverage:
	./.venv/bin/coverage erase
	CODEX_SUBPROCESS_COVERAGE=1 ./.venv/bin/coverage run -m pytest tests/test_update_codex_metrics.py tests/test_update_codex_metrics_domain.py tests/test_history_audit.py tests/test_reporting.py
	./.venv/bin/coverage combine
	./.venv/bin/coverage report -m

dev-refresh-local:
	./.venv/bin/python -m pip install --no-deps --no-build-isolation -e .

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
