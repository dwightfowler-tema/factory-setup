# Changelog

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
