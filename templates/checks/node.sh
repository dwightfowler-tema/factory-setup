#!/usr/bin/env bash
# Starting point for a Node project. Keep only the steps this repo really has.
# A test that does not run is a FAILURE: never tolerate skips (no `|| true`).
set -euo pipefail
if   [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile
elif [ -f yarn.lock ];      then yarn install --frozen-lockfile
else                             npm ci --prefer-offline; fi
npm run lint
npm run typecheck
out="$(mktemp)"; trap 'rm -f "$out"' EXIT
npm test -- --run 2>&1 | tee "$out"
if grep -Eiq '[0-9]+ (skipped|todo|pending)' "$out"; then
  echo "FAIL: tests did not run (skipped/todo/pending). A skipped test is a failure." >&2
  exit 1
fi
npm run build
