.PHONY: help validate-cli-output validate-cli-output-one

help:
	@echo "Available targets:"
	@echo "  make validate-cli-output               # Validate all CLI output fixtures"
	@echo "  make validate-cli-output-one FILE=...  # Validate one CLI output JSON file"

validate-cli-output:
	./scripts/validate_cli_output_fixtures.sh

validate-cli-output-one:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make validate-cli-output-one FILE=path/to/output.json"; \
		exit 2; \
	fi
	./scripts/validate_cli_output.sh "$(FILE)"
