---
name: factory-setup
description: Install, repair or upgrade the software factory in the current git repo. Use when the user types /factory-setup (init, checks, upgrade), or asks to bring the software factory into a project, rebuild factory/checks.sh, or update an installed factory.
---

# Factory setup

**Before doing anything else, Read `INSTALL.md` in this skill's directory (the
base directory shown when the skill loaded) in full, and follow it.** This file
only chooses the mode and sets the rules; the steps live in `INSTALL.md`.

You install the software factory (the `/factory` skill, its eight agents and the
`factory/` scripts) into the repo the user started `claude` in. A script does the
deterministic work; you do the judgment: choosing real checks, tailoring prompts,
and telling the user what you found.

```
/factory-setup            same as init if nothing is installed, else upgrade
/factory-setup init       first install
/factory-setup checks     re-derive and re-verify factory/checks.sh
/factory-setup upgrade    bring an installed factory up to this skill's version
```

With no argument: if `factory/VERSION` exists use `upgrade`, else `init`. Never
run `init` over an existing install.

## Rules

- Stay on the branch the user is on. Don't create or check out another branch.
- Never push, and never change anything on GitHub (labels), without showing the
  user first and asking. `labels` and `upgrade-apply` are dry runs until `--yes`.
- Learn the script's interface from top-level `SCRIPT --help`, which lists every
  command. Never discover it by passing flags to a subcommand.
- Never hand-edit `factory/config.json`; use `SCRIPT config set`.
- `checks.sh` is the factory's gate and the factory can never edit it. Writing it
  is the most important step: show the user the result.
- Commit only the files the install added or changed, by explicit path.
- Never edit the copied `factory/bin/*`, `.claude/skills/factory/SKILL.md`, or an
  agent's structure, file name, first-line format or one-line reply.
