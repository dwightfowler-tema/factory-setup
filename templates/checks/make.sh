#!/usr/bin/env bash
# Starting point when the repo already has make targets for its checks.
set -euo pipefail
make lint
make test
make build
