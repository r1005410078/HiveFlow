RUST_CLI_DIR := cli
COMPOSE := docker compose

.PHONY: help sync test lint architecture-check rust-test validate-cli-output validate-cli-output-one check run-pipeline run-server run-server-dev db-up db-down db-logs db-psql db-reset-db-volume db-init-env db-migrate

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
	@echo "  make run-server-dev                 # Run quant HTTP server with auto-reload"
	@echo "  make run-pipeline AS_OF=YYYY-MM-DD  # Run daily pipeline command"
	@echo "  make db-init-env                    # Create .env.db from template"
	@echo "  make db-up                          # Start TimescaleDB with Docker"
	@echo "  make db-down                        # Stop TimescaleDB"
	@echo "  make db-logs                        # Tail TimescaleDB logs"
	@echo "  make db-psql                        # Open psql in TimescaleDB container"
	@echo "  make db-migrate                     # Apply all SQL migrations in quant/db/migrations"
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
