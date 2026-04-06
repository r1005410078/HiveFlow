RUST_CLI_DIR := cli
COMPOSE := docker compose

.PHONY: help sync test lint architecture-check rust-test validate-cli-output validate-cli-output-one check run-pipeline sync-default run-server restart-run-server run-server-dev db-up db-down db-logs db-psql db-reset-db-volume db-init-env db-migrate db-clear-l1

help:
	@echo "Available targets:"
	@echo "  make sync                           # Sync Python deps"
	@echo "  make test                           # Run Python tests"
	@echo "  make lint                           # Run Ruff"
	@echo "  make architecture-check             # Run architecture boundary tests"
	@echo "  make rust-test                      # Run Rust CLI tests"
	@echo "  make validate-cli-output            # Validate all CLI output fixtures"
	@echo "  make validate-cli-output-one FILE=... # Validate one CLI output JSON"
	@echo "  make check                          # test + lint + fixture validation + rust tests"
	@echo "  make run-server                     # Run quant HTTP server"
	@echo "  make restart-run-server             # Kill listener on HF_PORT (default 8000), then run-server"
	@echo "  make run-server-dev                 # Run quant HTTP server with auto-reload"
	@echo "  make run-pipeline AS_OF=YYYY-MM-DD  # Run daily pipeline command"
	@echo "  make sync-default [SYNC_DAYS=N]     # Sync default universe 1d bars (cargo run; needs server + config)"
	@echo "  make db-init-env                    # Create .env.db from template"
	@echo "  make db-up                          # Start TimescaleDB with Docker"
	@echo "  make db-down                        # Stop TimescaleDB"
	@echo "  make db-logs                        # Tail TimescaleDB logs"
	@echo "  make db-psql                        # Open psql in TimescaleDB container"
	@echo "  make db-migrate                     # Apply all SQL migrations in quant/db/migrations"
	@echo "  make db-clear-l1                    # TRUNCATE bars + sync_* (retest sync; needs db-up)"
	@echo "  make db-reset-db-volume             # Drop DB data volume (destructive)"

sync:
	cd quant && uv sync

test:
	cd quant && uv run python -m pytest -q

lint:
	cd quant && uv run ruff check .

architecture-check:
	cd quant && uv run pytest tests/architecture -q
	cd cli && cargo test --test architecture_rules

rust-test:
	cd $(RUST_CLI_DIR) && cargo test

validate-cli-output:
	./scripts/validate_cli_output_fixtures.sh

validate-cli-output-one:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make validate-cli-output-one FILE=path/to/output.json"; \
		exit 2; \
	fi
	./scripts/validate_cli_output.sh "$(FILE)"

check: test lint architecture-check validate-cli-output rust-test

db-init-env:
	@if [ -f ".env.db" ]; then \
		echo ".env.db already exists"; \
	else \
		cp .env.db.example .env.db; \
		echo "Created .env.db from template"; \
	fi

db-up:
	@if [ ! -f ".env.db" ]; then \
		echo "Missing .env.db, creating from template..."; \
		cp .env.db.example .env.db; \
	fi
	$(COMPOSE) up -d timescaledb
	@echo "TimescaleDB is starting. Check readiness with: make db-logs"

db-down:
	$(COMPOSE) down

db-logs:
	$(COMPOSE) logs -f timescaledb

db-psql:
	$(COMPOSE) exec timescaledb psql -U "$${POSTGRES_USER:-hiveflow}" -d "$${POSTGRES_DB:-hiveflow}"

db-migrate:
	@if [ ! -f ".env.db" ]; then \
		echo "Missing .env.db, creating from template..."; \
		cp .env.db.example .env.db; \
	fi
	@set -a; . ./.env.db; set +a; \
	for f in quant/db/migrations/*.sql; do \
		echo "Applying migration: $$f"; \
		cat "$$f" | $(COMPOSE) exec -T timescaledb psql -v ON_ERROR_STOP=1 -U "$${POSTGRES_USER:-hiveflow}" -d "$${POSTGRES_DB:-hiveflow}"; \
	done

# 清空 K 线与同步元数据（表结构保留），用于重新测 data sync
db-clear-l1:
	@if [ ! -f ".env.db" ]; then \
		echo "Missing .env.db (run: make db-init-env)"; exit 1; \
	fi
	@set -a; . ./.env.db; set +a; \
	echo "Truncating bars, sync_checkpoints, sync_runs, sync_run_symbol_failures..."; \
	cat scripts/db_clear_l1_stock_data.sql | $(COMPOSE) exec -T timescaledb psql -v ON_ERROR_STOP=1 -U "$${POSTGRES_USER:-hiveflow}" -d "$${POSTGRES_DB:-hiveflow}"

db-reset-db-volume:
	@echo "WARNING: This will remove Timescale data volume permanently."
	$(COMPOSE) down -v

run-server:
	@if [ -f ".env.db" ]; then \
		set -a; . ./.env.db; set +a; \
		$(MAKE) db-migrate; \
		cd quant && HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= HF_DB_HOST=$${HF_DB_HOST:-127.0.0.1} HF_DB_PORT=$${HF_DB_PORT:-5432} HF_HOST=$${HF_HOST:-0.0.0.0} HF_PORT=$${HF_PORT:-8000} uv run python bin/server.py; \
	else \
		cd quant && HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= HF_HOST=$${HF_HOST:-0.0.0.0} HF_PORT=$${HF_PORT:-8000} uv run python bin/server.py; \
	fi

# Stop whatever is listening on HF_PORT (default 8000), then start run-server in the foreground.
restart-run-server:
	@set -a; \
	if [ -f ".env.db" ]; then . ./.env.db; fi; \
	set +a; \
	PORT="$${HF_PORT:-8000}"; \
	PIDS=$$(lsof -tiTCP:$$PORT -sTCP:LISTEN 2>/dev/null || true); \
	if [ -n "$$PIDS" ]; then \
		echo "Stopping listener(s) on port $$PORT: $$PIDS"; \
		kill $$PIDS 2>/dev/null || true; \
		sleep 0.3; \
		PIDS2=$$(lsof -tiTCP:$$PORT -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$PIDS2" ]; then \
			echo "Force killing: $$PIDS2"; \
			kill -9 $$PIDS2 2>/dev/null || true; \
		fi; \
	else \
		echo "No listener on port $$PORT"; \
	fi
	$(MAKE) run-server

run-server-dev:
	@if [ -f ".env.db" ]; then \
		set -a; . ./.env.db; set +a; \
		$(MAKE) db-migrate; \
		cd quant && HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= HF_DB_HOST=$${HF_DB_HOST:-127.0.0.1} HF_DB_PORT=$${HF_DB_PORT:-5432} HF_HOST=$${HF_HOST:-0.0.0.0} HF_PORT=$${HF_PORT:-8000} uv run uvicorn interfaces.http.app:create_app --factory --reload --host "$${HF_HOST}" --port "$${HF_PORT}"; \
	else \
		cd quant && HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= HF_HOST=$${HF_HOST:-0.0.0.0} HF_PORT=$${HF_PORT:-8000} uv run uvicorn interfaces.http.app:create_app --factory --reload --host "$${HF_HOST}" --port "$${HF_PORT}"; \
	fi

run-pipeline:
	@if [ -z "$(AS_OF)" ]; then \
		echo "Usage: make run-pipeline AS_OF=YYYY-MM-DD"; \
		exit 2; \
	fi
	@if [ ! -f "$$HOME/.hiveflow/config.toml" ]; then \
		echo "Missing config: $$HOME/.hiveflow/config.toml"; \
		echo "Create it with at least:"; \
		echo "  server_url = \"http://127.0.0.1:8000\""; \
		echo "  timeout_ms = 10000"; \
		echo "  retry = 1"; \
		exit 2; \
	fi
	cd cli && cargo run -- pipeline daily --as-of "$(AS_OF)"

# 与 `make run-pipeline` 相同：通过 cargo run 调用 CLI，无需事先 cargo build 出固定路径二进制
TODAY := $(shell date +%Y-%m-%d)
SYNC_DAYS ?= 252

sync-default:
	@if [ ! -f "$$HOME/.hiveflow/config.toml" ]; then \
		echo "Missing config: $$HOME/.hiveflow/config.toml"; \
		echo "Create it with at least:"; \
		echo "  server_url = \"http://127.0.0.1:8000\""; \
		echo "  timeout_ms = 10000"; \
		echo "  retry = 1"; \
		exit 2; \
	fi
	cd $(RUST_CLI_DIR) && cargo run -- data sync \
		--universe default \
		--days $(SYNC_DAYS) \
		--end-date $(TODAY) \
		--timeframe 1d \
		--wait
