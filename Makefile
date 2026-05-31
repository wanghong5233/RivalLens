# Repo-root shortcuts — delegate to backend/
.PHONY: help up up-build down logs-api health
help:
	@$(MAKE) -C backend help

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
