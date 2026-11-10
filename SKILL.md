---
name: factory-setup
description: Install, repair or upgrade the software factory in the current git repo. Use when the user types /factory-setup (init, checks, upgrade), or asks to bring the software factory into a project, rebuild factory/checks.sh, or update an installed factory.
---

# Factory setup

You install the software factory (the `/factory` skill, its eight agents and the
`factory/` scripts) into the repo the user started `claude` in. A script does
the deterministic work; you do the judgment: choosing real checks, tailoring
prompts, and telling the user what you found.

`SCRIPT` below is `scripts/factory_setup.py` in **this skill's directory** (the
base directory shown when this skill loaded). Run it from the target repo's
root, e.g. `python3 <skill-dir>/scripts/factory_setup.py preflight`.

```
/factory-setup            same as init if nothing is installed, else upgrade
/factory-setup init       first install
/factory-setup checks     re-derive and re-verify factory/checks.sh
/factory-setup upgrade    bring an installed factory up to this skill's version
```

Decide the mode from the argument. With none: if `factory/VERSION` exists use
`upgrade`, else `init`. Never run `init` over an existing install.

## Rules

- Stay on the branch the user is on. Don't create or check out another branch.
- Never push, and never create labels, without telling the user first. Commit
  locally; ask before pushing.
- `checks.sh` is the factory's gate and the factory can never edit it. Treat
  writing it as the most important step: show the user the result.
- Never edit the copied `factory/bin/*`, `.claude/skills/factory/SKILL.md`, or
  an agent's structure, file name, first-line format or one-line reply.

## init

1. **Preflight.** `SCRIPT preflight`. On any FAIL stop and tell the user what to
   fix. The most common: `origin/<base>` doesn't exist because the default
   branch was never pushed.
2. **Copy.** `SCRIPT copy`. It refuses to overwrite and writes `factory/VERSION`
   plus `factory/.setup-manifest.json` (used by `upgrade`; commit both).
3. **Ignore and docs.** `SCRIPT gitignore`, then `SCRIPT agents-md`. If the
   AGENTS.md / CLAUDE.md is new or lacks them, add: how to set up a fresh
   checkout (install dependencies, env files), how to start the dev server on a
   given port if there is one, and the validation commands matching `checks.sh`.
4. **checks.sh.** Follow the *checks* procedure below.
5. **config.json.** Set `base_branch` (preflight prints `BASE_BRANCH=`), and
   `merge_method` to one the repo allows
   (`gh api repos/{owner}/{repo} --jq '{allow_merge_commit, allow_squash_merge, allow_rebase_merge}'`).
   Keep `protected_paths` as shipped: do not add the project's tests (features
   legitimately change them; the code reviewer catches weakened tests). Move
   `ports.base` if the project already uses 5100–5199. Leave `concurrency`,
   `max_rounds`, `routing`, `surface_reviewers` and prices alone unless asked.
6. **Tailor agents** without changing their structure, names or reply formats:
   `reviewer-security.md` (this project's hot spots: auth, data access, payments,
   webhooks, where input meets queries or HTML), `reviewer-ui.md` (where design
   tokens and shared components live), `reviewer-ux.md` (the app's kinds of
   users), `approver.md` (what a human must always see: add to ESCALATE),
   `intake.md` (one line under **Decide** on what the project is for).
7. **Labels.** `SCRIPT labels` (ask first; it creates three labels on GitHub).
8. **Verify.** `python3 -c "import json;json.load(open('factory/config.json'))"`;
   `factory/bin/job queue` runs without error; every `.claude/agents/*.md` has
   only the frontmatter keys `name`, `description`, `tools`, `model` (plus
   `hooks` on the builder); `git check-ignore factory/jobs/x .worktrees/x`
   prints both; `git status --porcelain --untracked-files=all` shows the skill,
   agents and `factory/` as committable.
9. **Hand over.** Commit on the current branch with a one-line message and show
   the diff. Ask before pushing: jobs branch from `origin/<base>`, so the install
   must be on the base branch on origin before the first run. Then tell the user:
   label one or two small issues `factory`, run `/factory run`; start with
   `concurrency: 1` and read every PR; intake runs on Fable once per issue and,
   depending on plan, may bill to usage credits.

## checks (also step 4 of init)

`factory/checks.sh` decides whether a branch is fit to review, and the gate runs
it in a **fresh worktree with no installed dependencies**. A wrong script either
blocks every job or lets bad code through, so be thorough.

1. **Find the commands.** `SCRIPT detect` lists what the repo has. Prefer what
   CI runs on pull requests (`.github/workflows`), then AGENTS.md / CLAUDE.md,
   then manifest scripts and make targets. `templates/checks/*.sh` are starting
   points, not answers.
2. **Write it.** Install dependencies if a fresh worktree needs them, then lint,
   typecheck, tests and build, whichever exist. Non-interactive, no watch modes,
   nothing that rewrites files (no `--fix`, no `--update-snapshots`), exit
   non-zero on any failure, keep `set -euo pipefail`. Keep it fast.
3. **Say what you left out.** Integration tests that need a database, Docker,
   network or secrets are the usual casualties. List what you excluded and why,
   so the user decides. Never silently drop coverage.
4. **Prove it can fail.** The checks run against committed code, so commit
   `checks.sh` first (or stash nothing else). Then
   `SCRIPT verify-checks --break <a real source file>`. It runs the script twice in
   clean throwaway worktrees (catches flakiness and missing install steps) and
   once with the file sabotaged (must fail). A script that exits 0 on broken code
   is worse than none: fix it before going on. If the repo has no tests or linter
   at all, say so plainly; the gate will only be as strong as the build.
5. **Show the user the final script** and the timings. It is protected, so this
   is the one deliberate review of what "passing" means here.

## upgrade

1. `SCRIPT upgrade-plan` (read-only). It compares the repo with this skill's
   payload using the install-time manifest.
2. Explain the buckets: `safe`/`new`/`missing` are untouched-since-install or absent;
   `adapted`/`modified`/`clash` have local changes.
3. With the user's go-ahead, `SCRIPT upgrade-apply` overwrites only `safe`, `new`
   and `missing` files and refreshes the manifest.
4. For each remaining file, `diff -u` the repo's copy against `payload/<file>`
   and merge by hand, preserving the project's tailoring. Never overwrite
   `checks.sh` or `config.json`: merge new keys only.
5. Run the init verify step, commit, and ask before pushing.
