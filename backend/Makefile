PROJECT ?= rivallens
COMPOSE_FILE ?= docker-compose.dev.yml
DC := docker compose -p $(PROJECT) -f $(COMPOSE_FILE)

SVC_API := rivallens_api
SVC_DB := rivallens_db

API_URL ?= http://localhost:8010
DB_NAME := rivallens_dev
DB_USER := postgres

.PHONY: help
help:
	@echo Usage: make [target]
	@echo
	@echo Common:
	@echo "  up             Start containers without build"
	@echo "  up-build       Build and start containers"
	@echo "  down           Stop and remove containers"
	@echo "  logs-api       Follow backend logs"
	@echo "  db-shell       Open psql shell"
	@echo "  migrate        Run alembic upgrade head"

.PHONY: up
up:
	$(DC) up -d --no-build

.PHONY: up-build
up-build:
	$(DC) up -d --build

.PHONY: down
down:
	$(DC) down --remove-orphans

.PHONY: down-v
down-v:
	$(DC) down --remove-orphans -v

.PHONY: stop
stop:
	$(DC) stop

.PHONY: restart
restart:
	$(DC) restart

.PHONY: restart-api
restart-api:
	$(DC) restart $(SVC_API)

.PHONY: rebuild-api
rebuild-api:
	$(DC) build $(SVC_API)
	$(DC) up -d --no-build --force-recreate --no-deps $(SVC_API)

.PHONY: build
build:
	$(DC) build

.PHONY: ps
ps:
	$(DC) ps

.PHONY: health
health:
	@curl -sS $(API_URL)/health || echo "api not responding at $(API_URL)"

.PHONY: logs
logs:
	$(DC) logs --tail=0 -f

.PHONY: logs-api
logs-api:
	$(DC) logs $(SVC_API) --tail=0 -f 2>&1 | grep --line-buffered -Ev '"(GET|HEAD) /health '

.PHONY: logs-api-history
logs-api-history:
	$(DC) logs $(SVC_API) --tail=200

.PHONY: logs-api-error
logs-api-error:
	$(DC) logs $(SVC_API) --tail=0 -f | grep --line-buffered -E "ERROR|WARNING|Traceback|Exception| 4[0-9][0-9] | 5[0-9][0-9] "

.PHONY: logs-db
logs-db:
	$(DC) logs $(SVC_DB) --tail=0 -f

.PHONY: shell
shell:
	$(DC) exec $(SVC_API) sh

.PHONY: db-shell
db-shell:
	$(DC) exec $(SVC_DB) psql -U $(DB_USER) -d $(DB_NAME)

.PHONY: migrate
migrate:
	$(DC) exec $(SVC_API) alembic upgrade head

.PHONY: db-tables
db-tables:
	@$(DC) exec -T $(SVC_DB) psql -U $(DB_USER) -d $(DB_NAME) -tAc "SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY table_schema, table_name;"

.PHONY: db-runs
db-runs:
	@$(DC) exec -T $(SVC_DB) psql -U $(DB_USER) -d $(DB_NAME) -c "SELECT run_id, status, created_at FROM runs ORDER BY created_at DESC LIMIT 20;"

.PHONY: db-clear
db-clear:
	@echo ">>> TRUNCATE public tables ..."
	@$(DC) exec -T $(SVC_DB) psql -U $(DB_USER) -d $(DB_NAME) -c "DO $$ DECLARE r RECORD; BEGIN FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname='public') LOOP EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE'; END LOOP; END $$;" || true
	@echo ">>> done."

.PHONY: docker-prune-soft
docker-prune-soft:
	docker system prune -f

.PHONY: docker-prune-hard
docker-prune-hard:
	docker system prune -f
	docker image prune -a -f
