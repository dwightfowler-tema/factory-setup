#!/usr/bin/env bash
# Starting point for a Python project. Keep only the steps this repo really has.
set -euo pipefail
python3 -m venv .venv-factory
. .venv-factory/bin/activate
pip install -q -e ".[dev]" 2>/dev/null || pip install -q -r requirements.txt
ruff check .
mypy .
pytest -q
