# Working agreements

## Branch hygiene
- After a pull request is merged successfully, delete its head branch on the remote and locally, then run `git pull --prune` (or `git fetch --prune`) so deleted branches disappear from the local clone.
- Before deleting, confirm the branch is fully merged: `git merge-base --is-ancestor origin/<branch> origin/<base>` must succeed. Never delete a branch that has unmerged commits.
- Merging a PR still needs the owner's explicit go-ahead.

## Before changing the skill
- Run `bash tests/smoke.sh`; it must print `SMOKE OK`.
- Bump `VERSION` and add a `CHANGELOG.md` entry for any user-visible change.
