#!/usr/bin/env bash
# Starting point for a Rust project.
set -euo pipefail
cargo clippy --all-targets -- -D warnings
cargo test
cargo build
