.PHONY: lint typecheck test verify verify-public-boundary setup-hooks

PYTHON ?= python3

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest tests/test_public_boundary.py

verify-public-boundary:
	PYTHONPATH=src $(PYTHON) -m codex_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml

setup-hooks:
	git config core.hooksPath .githooks

verify: lint typecheck test verify-public-boundary
