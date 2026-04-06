#!/usr/bin/env bash
set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "[ERROR] jq is required but not found." >&2
  exit 2
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <output.json>" >&2
  exit 2
fi

FILE="$1"
if [[ ! -f "$FILE" ]]; then
  echo "[ERROR] File not found: $FILE" >&2
  exit 2
fi

# Basic parse
jq . "$FILE" >/dev/null

# Required keys
jq -e '
  has("schema_version") and
  has("command") and
  has("run_id") and
  has("status") and
  has("generated_at") and
  has("source") and
  has("advice_only") and
  has("decision_weight") and
  has("data") and
  has("warnings") and
  has("errors")
' "$FILE" >/dev/null

# Type + enum checks + semver + iso8601-ish timestamp
jq -e '
  (.schema_version | type == "string" and test("^[0-9]+\\.[0-9]+\\.[0-9]+$")) and
  (.command | type == "string" and length > 0) and
  (.run_id | type == "string" and length > 0) and
  (.status | type == "string" and IN("ok","warning","error")) and
  (.generated_at | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T")) and
  (.source | type == "string" and IN("system","news_system","web_search")) and
  (.advice_only | type == "boolean") and
  (.decision_weight | type == "number" and . >= 0 and . <= 1) and
  (.warnings | type == "array") and
  (.errors | type == "array")
' "$FILE" >/dev/null

# Source semantics
jq -e '
  if .source == "web_search" then
    (.advice_only == true and .decision_weight == 0)
  else
    (.advice_only == false and .decision_weight == 1)
  end
' "$FILE" >/dev/null

# Command-specific semantics
jq -e '
  if .command == "hf factor optimize" then
    (.data | type == "object") and
    (.data | has("factor_names")) and
    (.data | has("analysis")) and
    (.data | has("correlation_analysis")) and
    (.data | has("top_combinations")) and
    (.data | has("release_gate")) and
    (.data | has("report")) and
    (.data | has("recommendations")) and
    (.data.release_gate | type == "object") and
    (.data.release_gate.status | type == "string" and IN("pass","watch","fail")) and
    (.data.release_gate.blocking_reasons | type == "array" and all(.[]; type == "string")) and
    (.data.release_gate.watch_items | type == "array" and all(.[]; type == "string")) and
    (.data.report | type == "object")
  elif .command == "hf monitor health-report" then
    (.data | type == "object") and
    (.data | has("as_of")) and
    (
      if .data.skipped == true then
        (.data | has("skipped")) and
        (.data | has("overall_rating")) and
        (.data.overall_rating == null) and
        (.data | has("factor_health")) and
        (.data.factor_health == null)
      else
        (.data | has("overall_rating")) and
        (.data | has("factor_health")) and
        (.data | has("signal_health")) and
        (.data | has("risk_health")) and
        (.data | has("trend")) and
        (.data | has("run_daily_warnings")) and
        (.data.factor_health | type == "object") and
        (.data.signal_health | type == "object") and
        (.data.risk_health | type == "object") and
        (.data.run_daily_warnings | type == "array")
      end
    )
  else
    true
  end
' "$FILE" >/dev/null

echo "[OK] $FILE passed HiveFlow CLI output validation."
