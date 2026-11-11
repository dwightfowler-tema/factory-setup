#!/usr/bin/env bash
# Starting point for a Python project managed with uv (uv.lock present).
# Keep only the steps this repo really has. A test that does not run is a
# FAILURE: never tolerate skips (no `|| true`), and never exclude tests with
# markers or addopts (`-m "not expensive"` is a test that did not run).
set -euo pipefail
uv sync --frozen
# uv run --frozen ruff check .      # only if the project configures ruff
# uv run --frozen mypy .            # only if the project configures mypy/pyright
out="$(mktemp)"; trap 'rm -f "$out"' EXIT
uv run --frozen pytest -q -rs 2>&1 | tee "$out"
if grep -Eq '[0-9]+ (skipped|xfailed|xpassed|deselected)' "$out"; then
  echo "FAIL: tests did not run (skipped/xfailed/xpassed/deselected). A skipped test is a failure." >&2
  exit 1
fi
# uv build                          # only if the project is packaged
