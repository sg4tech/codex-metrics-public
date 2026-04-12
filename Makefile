.PHONY: init check-init remind-task lint typecheck test verify build-check security bandit complexity arch-check verify-public-boundary setup-hooks dev-refresh-local package package-standalone package-refresh-local package-refresh-global live-usage-smoke public-overlay-status public-overlay-bootstrap public-overlay-verify public-overlay-push public-overlay-pull sync-bootstrap-policy

PYTHON3 ?= python3

init:
	git pull origin master || true
	$(PYTHON3) -m venv .venv
	.venv/bin/pip install -U pip setuptools wheel
	.venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e .
	@$(MAKE) remind-task
	@$(MAKE) public-overlay-pull || true

check-init:
	@test -d .venv || $(MAKE) init

remind-task:
	@echo ""
	@echo "reminder: before starting engineering work, run: ./tools/ai-agents-metrics start-task --title '...' --task-type <product|meta|retro>"
	@echo ""

lint: remind-task
	./.venv/bin/ruff check .

typecheck: remind-task
	./.venv/bin/mypy src scripts

test: remind-task
	./.venv/bin/python -m pytest tests/

build-check:
	./.venv/bin/pip install --no-deps -e . -q

complexity: check-init
	@echo "=== Cyclomatic complexity report (rank C and above) ==="
	@.venv/bin/radon cc src/ -n C -s || true
	@echo "=== Maintainability index (rank C — hard to maintain) ==="
	@.venv/bin/radon mi src/ -n C -s || true

arch-check: check-init
	PYTHONPATH=src .venv/bin/lint-imports

sync-bootstrap-policy:
	cp docs/ai-agents-metrics-policy.md src/ai_agents_metrics/data/bootstrap_codex_metrics_policy.md

build-check: sync-bootstrap-policy
	./.venv/bin/pip install --no-deps -e . -q

verify: check-init remind-task lint security bandit typecheck test build-check complexity arch-check

security:
	./.venv/bin/python -m ai_agents_metrics security --repo-root . --rules-path config/security-rules.toml

bandit: remind-task
	./.venv/bin/bandit -r src scripts -q --skip B404,B607,B603

verify-public-boundary:
	./.venv/bin/python -m ai_agents_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml

setup-hooks:
	git config core.hooksPath .githooks

dev-refresh-local:
	./.venv/bin/python -m pip install --no-deps --no-build-isolation -e .

package: sync-bootstrap-policy
	rm -rf build dist src/ai_agents_metrics.egg-info
	./.venv/bin/python -m build --no-isolation

package-standalone:
	rm -rf build/standalone dist/standalone
	./.venv/bin/python scripts/build_standalone.py

package-refresh-local: package
	./.venv/bin/python -m pip install --no-deps --force-reinstall dist/*.whl

package-refresh-global: package-refresh-local package-standalone
	./dist/standalone/ai-agents-metrics install-self $(INSTALL_SELF_ARGS)

live-usage-smoke:
	./.venv/bin/python scripts/check_live_usage_recovery.py

public-overlay-status:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . status

public-overlay-bootstrap:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . bootstrap --public-repo git@github.com:sg4tech/codex-metrics-public.git

public-overlay-verify:
	./.venv/bin/python -m ai_agents_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml

public-overlay-pull:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . pull --execute

public-overlay-push: public-overlay-pull
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . push --execute

coverage:
	./.venv/bin/coverage erase
	CODEX_SUBPROCESS_COVERAGE=1 ./.venv/bin/coverage run -m pytest tests/
	./.venv/bin/coverage combine
	./.venv/bin/coverage report -m
