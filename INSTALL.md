# Installing the software factory with /factory-setup

The detailed procedure for `init`, `checks` and `upgrade`. `SKILL.md` chooses the
mode and holds the rules; this file holds the steps and the gotchas. Follow it
in full.

`SCRIPT` means `scripts/factory_setup.py` in this skill's directory (the base
directory shown when the skill loaded), run from the **target repo's root**:
`python3 <skill-dir>/scripts/factory_setup.py <command>`. Learn the commands
from `SCRIPT --help`.

## init

1. **Preflight.** `SCRIPT preflight`. On any FAIL stop and tell the user what to
   fix. Common ones: `origin/<base>` doesn't exist because the default branch was
   never pushed.
   - On a WARN about staged or uncommitted changes, tell the user the install
     should start from a committed tree (see *checks*, step 4).
   - On a WARN that HEAD is ahead of `origin/<base>`: jobs branch from
     `origin/<base>`, so everything `checks.sh` depends on (lockfile, tests,
     config), not just the factory files, must be pushed there before the first run.
2. **Copy.** `SCRIPT copy`. It refuses to overwrite and writes `factory/VERSION`
   plus `factory/.setup-manifest.json` (used by `upgrade`; commit both).
3. **Ignore and docs.** `SCRIPT gitignore`, then `SCRIPT agents-md`. If the
   AGENTS.md / CLAUDE.md is new or lacks them, add: how to set up a fresh
   checkout (install dependencies, env files), how to start the dev server on a
   given port if there is one, and the validation commands matching `checks.sh`.
4. **checks.sh.** Follow the *checks* procedure below.
5. **config.json.** Never hand-edit it. Change only keys that differ from the
   shipped defaults, using `SCRIPT config set <dotted.key> <value>`:
   - `base_branch`: preflight prints `BASE_BRANCH=`.
   - `merge_method`: one the repo allows
     (`gh api repos/{owner}/{repo} --jq '{allow_merge_commit, allow_squash_merge, allow_rebase_merge}'`).
   - `ports.base`: move it if the project already uses 5100–5199.
   - Keep `protected_paths` as shipped: don't add the project's tests (features
     legitimately change them; the code reviewer catches weakened tests).
   - Leave `concurrency`, `max_rounds`, `routing`, `surface_reviewers` and prices
     alone unless the user asks.
   `config get <key>` reads a value. Setting a key that doesn't exist is an
   error unless `--add`.
6. **Tailor agents** without changing their structure, names or reply formats:
   `reviewer-security.md` (this project's hot spots: auth, data access, payments,
   webhooks, where input meets queries or HTML), `reviewer-ui.md` (where design
   tokens and shared components live), `reviewer-ux.md` (the app's kinds of
   users), `approver.md` (what a human must always see: add to ESCALATE),
   `intake.md` (one line under **Decide** on what the project is for).
7. **Labels.** `SCRIPT labels` is a dry run: it lists the three labels and which
   already exist, and changes nothing. Show the user, ask, then `SCRIPT labels --yes`.
   It is idempotent (re-running updates in place). To remove a label later:
   `gh label delete <name>`.
8. **Verify.** `SCRIPT config get base_branch` succeeds; `factory/bin/job queue`
   runs without error; every `.claude/agents/*.md` has only the frontmatter keys
   `name`, `description`, `tools`, `model` (plus `hooks` on the builder);
   `git check-ignore factory/jobs/x .worktrees/x` prints both; and
   `git status --porcelain --untracked-files=all` shows the skill, agents and
   `factory/` as committable.
9. **Hand over.** Stay on the user's branch. Commit **only the files the install
   added or changed, by explicit path** (`git commit -- <paths>`), never a bare
   `git commit`, which sweeps up whatever the user already staged. If a file the
   user already had staged (such as `.gitignore`) is among them, say so. Show the
   diff, and ask before pushing: jobs branch from `origin/<base>`, so the install
   (and everything `checks.sh` depends on) must be on the base branch on origin
   before the first run. Then tell the user:
   - label one or two small issues `factory`, then run `/factory run`;
   - start with `concurrency: 1` and read every PR until trusted;
   - intake runs on Fable once per issue and, depending on plan, may bill to usage credits;
   - the dashboard is served from the target project: `cd factory && python3 -m http.server`,
     then `http://localhost:8000/dashboard.html`. It reads that project's `factory/jobs/`;
   - `factory/checks.sh` and `factory/config.json` are protected, so the factory can
     never add a lint step itself, and the tailored approver escalates dependency
     changes. Tooling changes such as adding a linter are better done by a human
     directly than as a factory issue.

## checks (also step 4 of init)

`factory/checks.sh` decides whether a branch is fit to review. The placeholder
the payload ships (it exits 1) must be replaced here. The gate runs the script in
a **fresh worktree with no installed dependencies**. A wrong script either blocks
every job or lets bad code through, so be thorough.

1. **Find the commands.** `SCRIPT detect` lists what the repo has. Prefer what CI
   runs on pull requests (`.github/workflows`), then AGENTS.md / CLAUDE.md, then
   manifest scripts and make targets. `templates/checks/*.sh` (`node`, `python`,
   `python-uv`, `go`, `rust`, `make`) are starting points, not answers.
2. **Write it.** Install dependencies if a fresh worktree needs them, then lint,
   typecheck, tests and build, whichever exist. Non-interactive, no watch modes,
   nothing that rewrites files (no `--fix`, no `--update-snapshots`), exit non-zero
   on any failure, keep `set -euo pipefail`. Keep it fast.
3. **Say what you left out.**
   - Integration tests that need a database, Docker, network or secrets are the
     usual casualties; list what you excluded (including excluded test markers)
     and why, so the user decides. Never silently drop coverage.
   - If `detect` reported GAPS (no linter, no typechecker), tell the user plainly
     that the gate is only as strong as the tests and the build, and offer to add
     a linter as a separate, human-reviewed change. Not a factory issue:
     `checks.sh` is protected and dependency changes escalate.
4. **Prove it can fail.** `verify-checks` tests the **committed** state (HEAD) in
   clean throwaway worktrees, like the gate. So commit `factory/checks.sh` first,
   and the project's own pending work too (lockfile, tests, pyproject changes);
   otherwise the clean runs fail for unrelated reasons and the result means
   nothing. `verify-checks` refuses on a dirty tree. Then
   `SCRIPT verify-checks --break <a real source file>`. It runs the script twice
   cleanly (catches flakiness and missing install steps) and once with the file
   sabotaged (must fail), printing the sabotage output so a vacuous pass is
   visible: read it, the failure should point at the broken file. A script that
   exits 0 on broken code is worse than none. If the repo has no tests or linter
   at all, say so plainly.
5. **Show the user the final script** and the timings. It is protected, so this is
   the one deliberate review of what "passing" means here.

## upgrade

1. `SCRIPT upgrade-plan` (read-only). It compares the repo with this skill's
   payload using the install-time manifest.
2. Explain the buckets: `safe`/`new`/`missing` are untouched-since-install or
   absent. `adapted`/`modified`/`clash` have local changes. `project-owned`
   (`factory/checks.sh`, `factory/config.json`) are never overwritten.
3. `SCRIPT upgrade-apply` is a dry run. With the user's go-ahead, run
   `SCRIPT upgrade-apply --yes`: it overwrites only `safe`, `new` and `missing`
   files and refreshes the manifest.
4. For each held file, `diff -u` the repo's copy against `payload/<file>` and merge
   by hand, preserving the project's tailoring. For `config.json` merge new keys
   with `config set --add`.
5. Run the init verify step, commit by explicit path, and ask before pushing.
