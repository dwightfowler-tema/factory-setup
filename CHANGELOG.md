# Changelog

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
