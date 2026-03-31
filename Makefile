RUST_CLI_DIR := cli

.PHONY: help sync test lint rust-test validate-cli-output validate-cli-output-one check run-pipeline

help:
	@echo "Available targets:"
	@echo "  make sync                           # Sync Python deps"
	@echo "  make test                           # Run Python tests"
	@echo "  make lint                           # Run Ruff"
	@echo "  make rust-test                      # Run Rust CLI tests"
	@echo "  make validate-cli-output            # Validate all CLI output fixtures"
	@echo "  make validate-cli-output-one FILE=... # Validate one CLI output JSON"
	@echo "  make check                          # test + lint + fixture validation + rust tests"
	@echo "  make run-pipeline AS_OF=YYYY-MM-DD  # Run daily pipeline command"

sync:
	cd quant && uv sync

test:
	cd quant && uv run python -m pytest -q

lint:
	cd quant && uv run ruff check .

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

check: test lint validate-cli-output rust-test

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
