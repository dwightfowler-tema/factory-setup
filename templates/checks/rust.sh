#!/usr/bin/env bash
# Starting point for a Rust project. A test that does not run is a FAILURE.
set -euo pipefail
cargo clippy --all-targets -- -D warnings
out="$(mktemp)"; trap 'rm -f "$out"' EXIT
cargo test 2>&1 | tee "$out"
if grep -Eq '[1-9][0-9]* ignored' "$out"; then
  echo "FAIL: tests were ignored (#[ignore]). An ignored test is a failure." >&2
  exit 1
fi
cargo build
