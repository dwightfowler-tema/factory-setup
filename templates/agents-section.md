<!-- factory-setup:begin -->
## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → approve, one PR per issue. State is in
`factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: from the repo root run `factory/bin/dashboard start`
(also `stop` and `status`; or `/factory dashboard`), then open the URL it prints
(http://127.0.0.1:8000/dashboard.html by default). It is bound to localhost and
keeps running after the chat ends, so stop it when you're done.

Each job works in its own git worktree, a full checkout of the repo at
`.worktrees/<job-id>` (gitignored). A tool run from the repo root that doesn't
read `.gitignore` sees those copies too; exclude `.worktrees/` in its config.

The gate does not accept skipped tests: a skipped, xfailed, deselected or
not-run test is a failure, not a pass.
<!-- factory-setup:end -->
