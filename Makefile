PRIVATE_OVERRIDE := 1
include oss/Makefile

# Override: delegate to oss/ where pyproject.toml lives, then mirror into root .venv
# so that root-level make targets (arch-check, build-check, complexity) have the tools.
init:
	cd oss && $(MAKE) init
	@test -d .venv || python3 -m venv .venv
	./.venv/bin/pip install -q -e "oss/[dev]"
	@echo ""
	@echo "AGENTS: all engineering work must be done inside oss/ — do not run make targets or CLI from the private root"
	@echo ""

# Override: pyproject.toml lives in oss/, not root
build-check:
	./.venv/bin/pip install --no-deps -e oss/ -q

# Override: lint-imports needs pyproject.toml and PYTHONPATH relative to oss/
arch-check:
	PYTHONPATH=src ./.venv/bin/lint-imports --config oss/pyproject.toml

# Override: pylint auto-discovery skips the pyproject.toml in oss/ when it is
# invoked from the private root, so pass the config path explicitly.
pylint-check:
	./.venv/bin/pylint --rcfile=oss/pyproject.toml src/

# When run from the private repo, check the oss/ subtree specifically
public-overlay-verify:
	./.venv/bin/python -m ai_agents_metrics verify-public-boundary --repo-root oss --rules-path oss/config/public-boundary-rules.toml
