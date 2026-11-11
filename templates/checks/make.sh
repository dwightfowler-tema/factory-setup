#!/usr/bin/env bash
# Starting point when the repo already has make targets for its checks.
# Make sure `make test` itself fails on skipped tests; if it can't, capture its
# output and grep for skipped/deselected counts as in the other templates.
set -euo pipefail
make lint
make test
make build
