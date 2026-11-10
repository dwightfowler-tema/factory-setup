#!/usr/bin/env bash
# Exercises the deterministic script against a throwaway repo (no gh, no network).
set -euo pipefail
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
S="python3 $SKILL/scripts/factory_setup.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q -b main . && git config user.email t@t && git config user.name t
printf 'print("hi")\n' > app.py; git add -A; git commit -qm init
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

$S copy >/dev/null
[ -x factory/bin/job ] && [ -x factory/checks.sh ] || fail "exec bits"
[ "$(cat factory/VERSION)" = "$(cat "$SKILL/VERSION")" ] || fail "VERSION stamp"
$S copy 2>/dev/null && fail "second copy should refuse"
$S gitignore >/dev/null; $S gitignore | grep -q nothing || fail "gitignore not idempotent"
git check-ignore factory/jobs/x .worktrees/x >/dev/null || fail "ignore lines"
$S agents-md >/dev/null; $S agents-md | grep -q already || fail "agents-md not idempotent"
grep -q '## Software factory' AGENTS.md || fail "agents section"
$S detect >/dev/null

# placeholder checks.sh must fail; a real one must pass clean and fail when sabotaged
git add -A; git commit -qm install
$S verify-checks 2>/dev/null && fail "placeholder checks.sh should fail"
printf '#!/usr/bin/env bash\nset -euo pipefail\npython3 -m py_compile app.py\n' > factory/checks.sh
git commit -qam checks
$S verify-checks --break app.py >/dev/null || fail "real checks.sh should verify"
printf '#!/usr/bin/env bash\nexit 0\n' > factory/checks.sh; git commit -qam vacuous
$S verify-checks --break app.py >/dev/null 2>&1 && fail "vacuous checks.sh must be caught"

# upgrade: untouched file updates, tailored file is held
echo "# tailored" >> .claude/agents/approver.md
cp -r "$SKILL" "$T/skill2" && echo "# new" >> "$T/skill2/payload/factory/bin/route"
echo "# upstream" >> "$T/skill2/payload/.claude/agents/approver.md"
echo 0.2.0 > "$T/skill2/VERSION"
P="python3 $T/skill2/scripts/factory_setup.py"
$P upgrade-plan | grep -q 'safe .*factory/bin/route' || fail "route should be safe"
$P upgrade-plan | grep -q 'adapted .*approver.md' || fail "approver should be adapted"
$P upgrade-apply | grep -q 'still to merge by hand: .*approver.md' || fail "apply should hold approver"
tail -1 factory/bin/route | grep -q '# new' || fail "route not updated"
tail -1 .claude/agents/approver.md | grep -q tailored || fail "approver was overwritten"
echo "SMOKE OK"
