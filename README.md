# factory-setup

A Claude Code skill that installs, repairs and upgrades the
[software factory](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2)
in any git repo you start `claude` in.

```
/factory-setup            init if nothing is installed, else upgrade
/factory-setup init       preflight, copy, adapt checks.sh/config/agents, labels, verify
/factory-setup checks     re-derive factory/checks.sh and prove it can fail
/factory-setup upgrade    bring an installed factory up to this skill's version
```

## Install the skill

```bash
git clone https://github.com/dwightfowler-tema/factory-setup ~/prj/factory-setup
ln -s ~/prj/factory-setup ~/.claude/skills/factory-setup
```

Update with `git pull`. Or clone straight to `~/.claude/skills/factory-setup`.

## How it's split

- `SKILL.md`: the procedure the agent follows (judgment: which checks, tailoring, what to tell you).
- `scripts/factory_setup.py`: the deterministic parts (preflight, copy, manifest, gitignore, labels, check detection, sabotage verification, upgrade classification). Stdlib only.
- `payload/`: the generic factory files, copied verbatim into a target repo.
- `templates/`: `checks.sh` starting points per stack and the AGENTS.md section.
- `VERSION`: stamped into each target as `factory/VERSION`, with a manifest of file hashes so `upgrade` can tell untouched files from tailored ones.

The runtime still lives inside each target repo (`factory/bin/*` locate the repo
by their own path, and the builder hook points at `$CLAUDE_PROJECT_DIR/factory/bin/gate`).
This skill only plants and maintains it.

## Tests

```bash
bash tests/smoke.sh
```

## Credit and license

`payload/` is derived from ZazenCodes' `software-factory-claude-code-v2`
(see `NOTICE`). GPLv3, see `LICENSE`.
