#!/usr/bin/env bash
# Starting point for a Go project. A test that does not run is a FAILURE.
set -euo pipefail
go vet ./...
out="$(mktemp)"; trap 'rm -f "$out"' EXIT
go test -v ./... 2>&1 | tee "$out"
if grep -Eq '^\s*--- SKIP' "$out"; then
  echo "FAIL: tests were skipped (t.Skip). A skipped test is a failure." >&2
  exit 1
fi
go build ./...
