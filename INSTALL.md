# Installing the software factory with /factory-setup

The detailed procedure for `init`, `checks` and `upgrade`. `SKILL.md` chooses the
mode and holds the rules; this file holds the steps and the gotchas. Follow it
in full.

`SCRIPT` means `scripts/factory_setup.py` in this skill's directory (the base
directory shown when the skill loaded), run from the **target repo's root**:
`python3 <skill-dir>/scripts/factory_setup.py <command>`. Learn the commands
from `SCRIPT --help`.

After editing this skill, run `/reload-skills` in any running session; a restart is
not needed.

## init

1. **Preflight.** `SCRIPT preflight`. On any FAIL stop and tell the user what to
   fix. Common ones: `origin/<base>` doesn't exist because the default branch was
   never pushed.
   - On a WARN about staged or uncommitted changes, tell the user the install
     should start from a committed tree (see *checks*, step 5).
   - On a WARN that HEAD is ahead of `origin/<base>`: jobs branch from
     `origin/<base>`, so everything `checks.sh` depends on (lockfile, tests,
     config), not just the factory files, must be pushed there before the first run.
2. **Copy.** `SCRIPT copy`. It refuses to overwrite and writes `factory/VERSION`
   plus `factory/.setup-manifest.json` (used by `upgrade`; commit both).
3. **Ignore and docs.** `SCRIPT gitignore`, then `SCRIPT agents-md`. The section
   it writes sits between `<!-- factory-setup:begin/end -->` markers, so re-running
   `agents-md` refreshes it in place (an older section without markers needs
   `agents-md --migrate`). If the AGENTS.md / CLAUDE.md is new or lacks them, add: how to set up a fresh
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
   - the dashboard reads the project's `factory/jobs/`. From the repo root (never `cd` into
     `factory/`: that moves your session's working directory) run `factory/bin/dashboard start`
     (or `/factory dashboard`). It serves on 127.0.0.1 only, port `dashboard.port` in `config.json`
     (default 8000), in the background, and prints the URL. It keeps running after the chat ends:
     `factory/bin/dashboard status` checks it and `factory/bin/dashboard stop` stops it by its
     recorded PID (never by process name). Nothing stops it automatically; a session-end hook in
     the user's own settings is the user's choice, not something this skill installs;
   - the gate does not accept skipped tests: a skipped, xfailed, deselected or not-run
     test is a failure, never a pass;
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
3. **Never tolerate skips.** The owner's rule: **a test must never be skipped
   because the system is misconfigured (that is a failure), and a test is never
   reported as successful unless it ran and passed.** A skipped, xfailed,
   deselected or not-run test is not a pass. Runners often exit 0 when tests only
   skip ("1 passed, 1 skipped"), so an exit code alone isn't enough:
   - **pytest:** run with `-rs`, tee the output, and fail the script if the summary
     matches `[0-9]+ (skipped|xfailed|xpassed|deselected)`. The templates
     (`python.sh`, `python-uv.sh`) do exactly this. Deselection counts: an
     `addopts` of `-m "not expensive"` is a test that did not run, so the gate must
     not allow it. Keep the guard in `checks.sh`, not in conftest: `checks.sh` is
     protected, so a factory agent can't weaken it.
   - **Other stacks:** jest/vitest `.skip`/`xit`/`todo`/`--testPathIgnorePatterns`,
     Go `t.Skip` (`go test -v`, grep `--- SKIP`), Rust `#[ignore]`: the templates
     show the grep for each. No `|| true` anywhere.
   - `SCRIPT detect` greps for these (and for deselecting config) and lists them
     under "TESTS THAT WOULD NOT RUN". Report them; fix them or ask the owner.
     Never quietly exclude them.
   - **Data-dependent tests.** A test that branches on what a real account or
     dataset happens to contain ("skip if the account has no playlists") must be
     restructured so every branch asserts something, preferably against stable
     public reference data.
   - **Costly tests** (live API calls that spend quota or money): do NOT quietly
     exclude them. Ask the owner to decide, showing the trade-off: (a) run it on
     every gate run (a job's gate runs about 4 or more times); (b) an offline
     contract test every gate plus one live run at the merge gate; (c) an offline
     contract test plus a live run on demand. Record the choice in a comment in
     `checks.sh` and in AGENTS.md. Warn that if the quota runs out the gate fails
     every job until it resets, which is correct, not a bug.
4. **Say what you left out.**
   - Integration tests that need a database, Docker, network or secrets are the
     usual casualties; list what you excluded and why, so the user decides. Never
     silently drop coverage, and never exclude a test by skipping or deselecting it
     (see step 3): an excluded test is a decision the owner makes.
   - If `detect` reported GAPS (no linter, no typechecker), tell the user plainly
     that the gate is only as strong as the tests and the build, and offer to add
     a linter as a separate, human-reviewed change. Not a factory issue:
     `checks.sh` is protected and dependency changes escalate.
5. **Prove it can fail.** `verify-checks` tests the **committed** state (HEAD) in
   clean throwaway worktrees, like the gate. So commit `factory/checks.sh` first,
   and the project's own pending work too (lockfile, tests, pyproject changes);
   otherwise the clean runs fail for unrelated reasons and the result means
   nothing. `verify-checks` refuses on a dirty tree. Then
   `SCRIPT verify-checks --break <a real source file>`. It runs the script twice
   cleanly (catches flakiness and missing install steps) and once with the file
   sabotaged (must fail). Each run's full output is saved and its log path printed;
   the summary drops install chatter (`+ pkg==x`, `Resolved`, `Downloading`, ...),
   shows the first error-looking line, and the last lines that remain. Read it: the
   failure should point at the broken file. A `WARN suspicious` means the sabotaged
   run failed fast without naming the file, so it may be an environment failure:
   read the full log before trusting it. A script that exits 0 on broken code is
   worse than none. If the repo has no tests or linter at all, say so plainly.
   `verify-checks` also reads each clean run's output for skipped, xfailed,
   xpassed, deselected, ignored or pending tests and FAILS if it finds any: a
   test that did not run is not a pass. (If the output shows no counts at all,
   the script isn't printing a summary: add `-rs`/`-v` so it does.)
   `verify-checks` refuses only for **tracked** changes (staged or modified);
   untracked files can't affect clean worktrees of HEAD, so it just notes them.
6. **Show the user the final script** and the timings. It is protected, so this is
   the one deliberate review of what "passing" means here.

## upgrade

1. `SCRIPT upgrade-plan` (read-only). It compares the repo with this skill's
   payload using the install-time manifest.
2. Explain the buckets: `safe`/`new`/`missing` are untouched-since-install or
   absent. `kept` are tailored files whose payload hasn't changed, so there is
   nothing to merge. `adapted`/`modified`/`clash` are tailored files whose payload
   changed, and `project-owned` (`factory/checks.sh`, `factory/config.json`) are
   never overwritten; the note says how many lines differ and whether the payload
   change is comments only.
3. `SCRIPT upgrade-apply` is a dry run. With the user's go-ahead, run
   `SCRIPT upgrade-apply --yes`: it overwrites only `safe`, `new` and `missing`
   files, refreshes the manifest and says exactly what it did.
4. For each held file, `diff -u` the repo's copy against `payload/<file>` and merge
   by hand, preserving the project's tailoring. For `config.json` merge new keys
   with `config set --add`. When the user has merged or declined, run
   `SCRIPT upgrade-apply --yes --mark-reviewed` so those files are flagged again
   only when the payload changes. (An install from before 0.3.0 has no record of
   what was reviewed: run it once if the plan lists files whose payload you know
   is unchanged.)
5. `upgrade-apply --yes` also makes sure `.gitignore` has the factory's lines (it
   appends any that are missing, such as `/factory/.dashboard.pid`).
   `upgrade-plan` flags a stale or unmarked factory section in AGENTS.md /
   CLAUDE.md (for example one that still names the old dashboard command): run
   `SCRIPT agents-md` (add `--migrate` for an old unmarked section) to refresh it.
6. Run the init verify step, commit by explicit path, and ask before pushing.
