.PHONY: lint security typecheck test verify verify-public-boundary setup-hooks init check-init

PYTHON = .venv/bin/python
PYTHON3 ?= python3

init:
	$(PYTHON3) -m venv .venv
	.venv/bin/pip install -U pip setuptools wheel
	.venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e .

check-init:
	@test -d .venv || $(MAKE) init

lint:
	$(PYTHON) -m ruff check .

security:
	PYTHONPATH=src $(PYTHON) -m codex_metrics security --repo-root . --rules-path config/security-rules.toml

typecheck:
	$(PYTHON) -m mypy src

test:
	PYTHONPATH=src $(PYTHON) -m pytest tests/test_public_boundary.py

verify-public-boundary:
	PYTHONPATH=src $(PYTHON) -m codex_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml

setup-hooks:
	git config core.hooksPath .githooks

verify: check-init lint security typecheck test verify-public-boundary
