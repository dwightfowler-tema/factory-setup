#!/usr/bin/env bash
# Starting point for a Python project managed with uv (uv.lock present).
# Keep only the steps this repo really has. If a test marker is excluded below,
# tell the user what it covers: the gate does not run it.
set -euo pipefail
uv sync --frozen
# uv run --frozen ruff check .      # only if the project configures ruff
# uv run --frozen mypy .            # only if the project configures mypy/pyright
uv run --frozen pytest -q
# uv build                          # only if the project is packaged
