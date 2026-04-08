.PHONY: lint security typecheck test verify verify-public-boundary setup-hooks

PYTHON ?= python3

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

verify: lint security typecheck test verify-public-boundary
