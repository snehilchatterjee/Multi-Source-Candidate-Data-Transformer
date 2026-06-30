#!/usr/bin/env bash

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/Users/snechatt/miniconda3/envs/ef/bin/python}"
SEPARATOR="================================================================================"
OVERALL_STATUS=0

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  echo "Set PYTHON_BIN to the Python executable from the ef environment." >&2
  exit 1
fi

run_case() {
  local case_name="$1"
  shift

  local case_dir="$SCRIPT_DIR/sample_dataset/$case_name"
  local expected="$case_dir/expected_output.json"
  local actual
  actual="$(mktemp)"

  echo "$SEPARATOR"
  echo "CASE: $case_name"
  echo "$SEPARATOR"
  echo
  echo "EXPECTED OUTPUT"
  echo "---------------"
  cat "$expected"
  echo
  echo "ACTUAL OUTPUT"
  echo "-------------"

  "$PYTHON_BIN" -m candidate_transformer "$@" --output "$actual"
  local exit_code=$?

  if [[ -f "$actual" ]]; then
    cat "$actual"
  else
    echo "No output file was produced."
  fi

  echo
  if [[ $exit_code -ne 0 ]]; then
    echo "RESULT: COMMAND FAILED (exit code $exit_code)"
    OVERALL_STATUS=1
  elif cmp -s "$expected" "$actual"; then
    echo "RESULT: MATCH"
  else
    echo "RESULT: MISMATCH"
    OVERALL_STATUS=1
  fi

  rm -f "$actual"
  echo
}

run_case "01_repeated" \
  --manifest "$SCRIPT_DIR/sample_dataset/01_repeated/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/01_repeated/config.json"

run_case "02_latest_email" \
  --manifest "$SCRIPT_DIR/sample_dataset/02_latest_email/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/02_latest_email/config.json"

run_case "03_negated_skills" \
  --manifest "$SCRIPT_DIR/sample_dataset/03_negated_skills/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/03_negated_skills/config.json"

run_case "04_email_corroboration" \
  --manifest "$SCRIPT_DIR/sample_dataset/04_email_corroboration/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/04_email_corroboration/config.json"

run_case "05_batch" \
  --manifest "$SCRIPT_DIR/sample_dataset/05_batch/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/05_batch/config.json"

run_case "06_missing_ids" \
  --manifest "$SCRIPT_DIR/sample_dataset/06_missing_ids/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/06_missing_ids/config.json"

run_case "07_no_manifest" \
  --csv "$SCRIPT_DIR/sample_dataset/07_no_manifest/applications.csv" \
  --note "$SCRIPT_DIR/sample_dataset/07_no_manifest/notes.txt" \
  --config "$SCRIPT_DIR/sample_dataset/07_no_manifest/config.json"

run_case "08_diagnostics" \
  --manifest "$SCRIPT_DIR/sample_dataset/08_diagnostics/manifest.json" \
  --config "$SCRIPT_DIR/sample_dataset/08_diagnostics/config.json" \
  --allow-partial

echo "$SEPARATOR"
if [[ $OVERALL_STATUS -eq 0 ]]; then
  echo "ALL DEMO CASES MATCHED"
else
  echo "ONE OR MORE DEMO CASES FAILED"
fi
echo "$SEPARATOR"

exit "$OVERALL_STATUS"
