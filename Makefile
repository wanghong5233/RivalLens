# Repo-root shortcuts — delegate to backend/
.PHONY: help setup up up-build down logs-api health
help:
	@$(MAKE) -C backend help

# Team-level safety bootstrap. New collaborators MUST run this on first checkout.
# 见 docs/private/engineering-playbook/02-secret-leakage-defense-layers.md
setup:
	@command -v pre-commit >/dev/null 2>&1 || python -m pip install --user pre-commit
	pre-commit install --hook-type pre-commit --hook-type pre-push
	@echo "[setup] pre-commit hooks installed (pre-commit + pre-push)"

up:
	@$(MAKE) -C backend up

up-build:
	@$(MAKE) -C backend up-build

down:
	@$(MAKE) -C backend down

logs-api:
	@$(MAKE) -C backend logs-api

health:
	@$(MAKE) -C backend health
