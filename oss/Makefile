.PHONY: init check-init remind-task lint typecheck test verify build-check security bandit complexity complexity-check arch-check pylint-check verify-public-boundary setup-hooks dev-refresh-local package package-standalone package-refresh-local package-refresh-global live-usage-smoke public-overlay-status public-overlay-bootstrap public-overlay-verify public-overlay-push public-overlay-pull sync-bootstrap-policy

PYTHON3 ?= python3

ifndef PRIVATE_OVERRIDE
init:
	git pull origin master || true
	$(PYTHON3) -m venv .venv
	.venv/bin/pip install -U pip setuptools wheel
	.venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e .
	@$(MAKE) remind-task
	@$(MAKE) public-overlay-pull || true
endif

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

ifndef PRIVATE_OVERRIDE
build-check:
	./.venv/bin/pip install --no-deps -e . -q
endif

complexity: check-init
	@echo "=== Cyclomatic complexity report (rank C and above) ==="
	@.venv/bin/radon cc src/ -n C -s || true
	@echo "=== Maintainability index (rank C — hard to maintain) ==="
	@.venv/bin/radon mi src/ -n C -s || true

# Hard gate: fail if any function reaches rank F (CC > 40).
# Advisory warnings for rank C+ are emitted by the 'complexity' target above.
complexity-check: check-init
	@echo "=== CC hard gate: rank F (CC > 40) must be empty ==="
	@.venv/bin/radon cc src/ -n F -s | grep . && exit 1 || true
	@echo "CC hard gate OK."

ifndef PRIVATE_OVERRIDE
arch-check: check-init
	PYTHONPATH=src .venv/bin/lint-imports
endif

sync-bootstrap-policy:
	@test -r src/ai_agents_metrics/data/bootstrap_codex_metrics_policy.md || { echo "ERROR: bootstrap policy not found (expected symlink to docs/)"; exit 1; }

PYLINT_IGNORE = cli.py,commands.py,ingest.py

pylint-check: check-init
	@echo "=== Pylint tier 1: hard-fail rules ==="
	./.venv/bin/pylint src/ --disable=all --enable=E0401,E0602,E1101,E1120,W0102,W0611,W0612,W0718,W1203,R0401,C0302 --ignore=$(PYLINT_IGNORE)
	@echo "=== Pylint tier 2: complexity warnings (advisory) ==="
	@.venv/bin/pylint src/ --disable=all --enable=R0912,R0913,R0914,R0915,R0902,W0401,C0411 --ignore=$(PYLINT_IGNORE) || true

verify: check-init remind-task sync-bootstrap-policy lint security bandit typecheck test build-check complexity complexity-check arch-check pylint-check

security:
	./.venv/bin/python -m ai_agents_metrics security --repo-root . --rules-path config/security-rules.toml

bandit: remind-task
	./.venv/bin/bandit -r src scripts -q --skip B404,B607,B603 --exclude scripts/permission_audit/test_*.py

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

ifndef PRIVATE_OVERRIDE
public-overlay-verify:
	./.venv/bin/python -m ai_agents_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml
endif

public-overlay-pull:
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . pull --execute

public-overlay-push: public-overlay-pull
	./.venv/bin/python scripts/public_overlay.py --private-repo-root . push --execute

coverage:
	./.venv/bin/coverage erase
	CODEX_SUBPROCESS_COVERAGE=1 ./.venv/bin/coverage run -m pytest tests/
	./.venv/bin/coverage combine
	./.venv/bin/coverage report -m
