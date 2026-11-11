#!/usr/bin/env bash
# Starting point for a Python project. Keep only the steps this repo really has.
# A test that does not run is a FAILURE: never tolerate skips (no `|| true`).
set -euo pipefail
python3 -m venv .venv-factory
. .venv-factory/bin/activate
pip install -q -e ".[dev]" 2>/dev/null || pip install -q -r requirements.txt
ruff check .
mypy .
out="$(mktemp)"; trap 'rm -f "$out"' EXIT
pytest -q -rs 2>&1 | tee "$out"
if grep -Eq '[0-9]+ (skipped|xfailed|xpassed|deselected)' "$out"; then
  echo "FAIL: tests did not run (skipped/xfailed/xpassed/deselected). A skipped test is a failure." >&2
  exit 1
fi
