#!/usr/bin/env bash
# Starting point for a Node project. Keep only the steps this repo really has.
set -euo pipefail
if   [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile
elif [ -f yarn.lock ];      then yarn install --frozen-lockfile
else                             npm ci --prefer-offline; fi
npm run lint
npm run typecheck
npm test -- --run
npm run build
