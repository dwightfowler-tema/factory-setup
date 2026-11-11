# Changelog

## 0.4.0
**Dashboard control**
- New `factory/bin/dashboard start|stop|status` (payload): serves `factory/` on 127.0.0.1 only, port `dashboard.port`
  in `config.json` (default 8000), in the background, PID in `factory/.dashboard.pid`. `stop` signals only that PID,
  after confirming it is this repo's http.server, and never kills by process name; a stale pid file kills nothing.
- `/factory dashboard [start|stop|status]` in the factory skill. Nothing stops the dashboard automatically.
- The AGENTS.md section is now wrapped in `<!-- factory-setup:begin/end -->` markers and uses `factory/bin/dashboard`.
  `agents-md` refreshes a marked section in place; `agents-md --migrate` replaces an old unmarked one.
  `upgrade-plan` flags a stale or unmarked section.
- `config set` now edits only the characters of the value (or inserts the new key next to its siblings in the
  same style) instead of re-indenting the whole file; the shipped compact formatting survives.
- `gitignore` also adds `/factory/.dashboard.pid` and `/factory/.dashboard.log`; `upgrade-apply --yes` adds any missing lines.

**Testing rule: never skip, never report a skip as a pass**
- INSTALL.md "checks": never tolerate skips (pytest `-rs` + guard, deselection counts, jest/vitest/Go/Rust
  equivalents), data-dependent tests must assert on every branch, and costly tests are an owner decision with three
  options (a/b/c), never quietly excluded.
- `detect` lists skipped/xfail/ignored tests and deselecting config under "TESTS THAT WOULD NOT RUN".
- `verify-checks` reads each clean run's output and FAILS on skipped, xfailed, xpassed, deselected, ignored or pending tests.
- `templates/checks/*`: skip guards, no `|| true`.
- Agent prompts (payload): `builder`, `reviewer-code` and `approver` treat a not-run test as a failure and report counts.

### Upgrade notes (installed projects)
| File | What you'll see on `upgrade-plan` |
|---|---|
| `factory/bin/dashboard` | `new`: applied by `upgrade-apply --yes` |
| `.claude/skills/factory/SKILL.md`, `.claude/agents/builder.md`, `.claude/agents/reviewer-code.md` | `safe` if untouched: applied by `--yes`; `adapted` if you tailored them: merge by hand |
| `.claude/agents/approver.md` | usually `adapted` (tailored): merge the two new "tests that did not run" bullets by hand |
| `factory/config.json` | `project-owned`, never overwritten. Optional: `config set dashboard.port 8000 --add` (the script defaults to 8000) |
| `factory/checks.sh` | unchanged payload, never overwritten. Add the skip guard yourself if it lacks one |
| AGENTS.md section | `agents-md` flagged as stale/legacy: run `agents-md` (or `--migrate`) |
| `.gitignore` | updated automatically by `upgrade-apply --yes` |
Then run `upgrade-apply --yes --mark-reviewed` once you've merged or declined the held files.

## 0.3.0
Skill-side changes only; installed projects need no file changes. The one install-time
artifact that changed is the dashboard command in the AGENTS.md section (see below).
- `verify-checks` saves each run's full log and prints its path, filters install noise from the
  summary, shows the first error line, and warns when a sabotaged run fails fast without naming the file.
- `verify-checks` (and `preflight`) refuse/warn only for tracked changes; untracked files are a NOTE.
- `upgrade-plan`/`upgrade-apply`: tailored files whose payload is unchanged are listed as `kept`
  ("nothing to merge"); changed ones show a line-diff count and whether the change is comments only;
  `upgrade-apply` says what it did and has `--mark-reviewed` so reviewed files aren't flagged forever.
  Installs from before 0.3.0 have no review record: run `upgrade-apply --yes --mark-reviewed` once.
- Dashboard command is now `python3 -m http.server 8000 --bind 127.0.0.1 -d factory` from the repo root
  (no `cd`, not exposed on the LAN, background, `pkill -f "http.server 8000"` to stop). The AGENTS.md
  section is written at install, so already-installed projects keep the old text; edit it by hand.
- Docs: `/reload-skills` note.

## 0.2.0
- `INSTALL.md` holds the detailed procedure; `SKILL.md` makes the session read it first.
- `labels` and `upgrade-apply` are dry runs until `--yes`. `--help` works anywhere and never runs a command; unknown flags are errors.
- New `config get|set [--add]`: atomic, validated edits of `factory/config.json`.
- `preflight` WARNs on a dirty tree and on HEAD ahead of `origin/<base>`. `verify-checks` refuses a dirty tree (`--allow-dirty` to override), skips the sabotage run when the clean runs fail, and prints the sabotage output.
- `detect` reports missing linters/typecheckers and points at the new `python-uv.sh` template when `uv.lock` exists.
- `upgrade-plan`/`upgrade-apply` treat `factory/checks.sh` and `factory/config.json` as project-owned: never overwritten. The only payload change is a comment in `checks.sh`.
- Docs: commit by explicit path, `labels` is idempotent (`gh label delete <name>` to remove), dashboard and protected-path notes.

## 0.1.0
- First release: payload, installer script, templates, smoke test.
