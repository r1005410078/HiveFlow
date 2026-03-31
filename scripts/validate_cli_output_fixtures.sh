#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATOR="$ROOT_DIR/scripts/validate_cli_output.sh"
FIXTURE_ROOT="$ROOT_DIR/quant/tests/fixtures/cli_output"

if [[ ! -x "$VALIDATOR" ]]; then
  echo "[ERROR] Validator not found or not executable: $VALIDATOR" >&2
  exit 2
fi

if [[ ! -d "$FIXTURE_ROOT/valid" || ! -d "$FIXTURE_ROOT/invalid" ]]; then
  echo "[ERROR] Fixture directories missing under: $FIXTURE_ROOT" >&2
  exit 2
fi

pass_count=0
fail_count=0

while IFS= read -r file; do
  if "$VALIDATOR" "$file" >/dev/null; then
    echo "[PASS] valid fixture accepted: $file"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] valid fixture rejected: $file"
    fail_count=$((fail_count + 1))
  fi
done < <(find "$FIXTURE_ROOT/valid" -type f -name '*.json' | sort)

while IFS= read -r file; do
  if "$VALIDATOR" "$file" >/dev/null 2>&1; then
    echo "[FAIL] invalid fixture accepted: $file"
    fail_count=$((fail_count + 1))
  else
    echo "[PASS] invalid fixture rejected: $file"
    pass_count=$((pass_count + 1))
  fi
done < <(find "$FIXTURE_ROOT/invalid" -type f -name '*.json' | sort)

echo "[SUMMARY] pass=$pass_count fail=$fail_count"

if [[ $fail_count -ne 0 ]]; then
  exit 1
fi
