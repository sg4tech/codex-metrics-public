.PHONY: lint typecheck test verify verify-public-boundary

lint:
	python -m ruff check .

typecheck:
	python -m mypy src

test:
	python -m pytest tests/test_public_boundary.py

verify-public-boundary:
	python -m codex_metrics verify-public-boundary --repo-root . --rules-path config/public-boundary-rules.toml

verify: lint typecheck test verify-public-boundary
